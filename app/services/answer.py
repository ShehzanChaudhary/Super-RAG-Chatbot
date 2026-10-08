import asyncio
import base64
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.core.config import settings
from app.prompts import get_prompt_template
from app.services.chart_service import chart_block, chart_service, detect_intent

ERROR_MESSAGE = "Error while generating the response. Try Again!"

# The LLM ends its reply with a line like "SOURCES: 1, 3"
SOURCES_MARKER = "SOURCES:"
HOLD_BACK = len(SOURCES_MARKER) - 1  # last characters are held back while streaming

# Chart images sent to the LLM along with the text (max per question)
MAX_VISION_IMAGES = 4
FAILED_CAPTION = "Image description unavailable"

IMAGE_BLOCK_RE = re.compile(r"\[IMAGE id=(\S+) page=\d+\]\s*(.*?)\s*\[/IMAGE\]", re.DOTALL)
CHART_WORDS_RE = re.compile(r"\b(chart|graph|figure|pie|bar|plot|map|infographic|axis|legend)\b", re.IGNORECASE)
VISUAL_QUESTION_RE = re.compile(
    r"\b(chart|graph|figure|plot|pie|bar|diagram|infographic|map|image|picture|visual|shown|depicted)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
FILE_YEAR_RE = re.compile(r"(\d{4})_(\d{2})")
FACT_SOURCE_RE = re.compile(r"source (\d+)")


def report_year(source_pdf: str) -> str:
    """Annual_Report_2023_24.pdf -> FY2024"""
    match = FILE_YEAR_RE.search(source_pdf)
    if not match:
        return source_pdf
    return "FY" + match.group(1)[:2] + match.group(2)


def numbers_in(text: str) -> set[str]:
    """Numbers with 3 or more digits (years are ignored). Written exactly as in the text."""
    found = set()
    for number in NUMBER_RE.findall(text):
        number = number.rstrip(",")
        digits = number.replace(",", "").replace(".", "")
        if len(digits) < 3:
            continue
        if re.fullmatch(r"20\d{2}", number):
            continue
        found.add(number)
    return found


class AnswerService:
    """Writes the answer from the retrieved pages, and decides the citations."""

    # ---------- Chart images ----------

    async def pick_images(self, question: str, chunks: list[dict]) -> list[dict]:
        """Chart images that should be shown to the LLM, so numbers are read from the real picture.

        An image is picked when its caption failed at ingestion, or when the question
        is about charts and the caption looks like a chart.
        """
        wants_visual = bool(VISUAL_QUESTION_RE.search(question))
        picked = []

        # Best pages first, because the number of images is limited
        for chunk in sorted(chunks, key=lambda c: c.get("score", 0), reverse=True):
            captions = {image_id: text for image_id, text in IMAGE_BLOCK_RE.findall(chunk["text"])}
            for image in chunk.get("images", []):
                caption = captions.get(image["image_id"], "")
                failed = FAILED_CAPTION in caption
                is_chart = bool(CHART_WORDS_RE.search(caption))
                if failed or (wants_visual and is_chart):
                    picked.append(
                        {
                            "image_id": image["image_id"],
                            "path": image["path"],
                            "source_pdf": chunk["source_pdf"],
                            "page": chunk["page_start"],
                        }
                    )
                if len(picked) >= MAX_VISION_IMAGES:
                    return picked
        return picked

    @staticmethod
    def read_image(path: str) -> str | None:
        file = Path(path)
        if not file.exists():
            logger.warning(f"Image file not found: {path}")
            return None
        return base64.b64encode(file.read_bytes()).decode("utf-8")

    async def build_messages(self, question: str, chunks: list[dict], images: list[dict]) -> list[dict]:
        # Images whose file is missing are dropped
        encoded = []
        for image in images:
            data = await asyncio.to_thread(self.read_image, image["path"])
            if data:
                encoded.append((image, data))

        prompt = get_prompt_template("answer.jinja2").render(
            question=question,
            chunks=chunks,
            images=[image for image, _ in encoded],
        )
        if not encoded:
            return [{"role": "user", "content": prompt}]

        content = [{"type": "text", "text": prompt}]
        for _, data in encoded:
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}", "detail": "high"}}
            )
        return [{"role": "user", "content": content}]

    # ---------- Reading the LLM reply ----------

    @staticmethod
    def split_answer(full: str) -> tuple[str, str | None]:
        """Cut the reply into (answer text, text after SOURCES:). The second is None if missing."""
        position = full.find(SOURCES_MARKER)
        if position == -1:
            return full.strip(), None
        return full[:position].strip(), full[position + len(SOURCES_MARKER):].strip()

    @staticmethod
    def build_citations(numbers: list[int], chunks: list[dict]) -> list[dict]:
        citations, seen = [], set()
        for number in numbers:
            chunk = chunks[number - 1]
            key = (chunk["source_pdf"], chunk["page_start"])
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "doc_name": chunk["source_pdf"],
                    "pdf_page": chunk["page_start"],
                    "report_year": report_year(chunk["source_pdf"]),
                    "chunk_type": "page",
                    "url": f"{settings.DOCUMENTS_URL}/{chunk['source_pdf']}#page={chunk['page_start']}",
                }
            )
        return citations

    @staticmethod
    def numbers_are_in_sources(answer: str, texts: list[str]) -> bool:
        """Every number of the answer must be written in the given texts."""
        source_text = " ".join(texts)
        missing = [n for n in numbers_in(answer) if n not in source_text]
        if missing:
            logger.warning(f"Numbers in the answer but not in the sources: {missing}")
        return not missing

    def finish(self, full: str, chunks: list[dict]) -> dict:
        """Everything we know after the LLM is done: answer, citations, found, verified."""
        answer, sources_line = self.split_answer(full)

        if sources_line is None:
            logger.warning("The reply has no SOURCES line")
            return {"answer": answer, "citations": [], "found": True, "verified": False}

        if "none" in sources_line.lower():
            return {"answer": answer, "citations": [], "found": False, "verified": True}

        numbers = []
        for text in re.findall(r"\d+", sources_line):
            number = int(text)
            if 1 <= number <= len(chunks) and number not in numbers:
                numbers.append(number)

        citations = self.build_citations(numbers, chunks)
        verified = bool(citations) and self.numbers_are_in_sources(answer, [c["text"] for c in chunks])
        return {"answer": answer, "citations": citations, "found": True, "verified": verified}

    # ---------- Forecast ----------

    async def forecast_answer(self, question: str, chunks: list[dict]) -> dict | None:
        """Forecast answer: numbers are collected from the pages and projected by code.

        Returns None when this is not a real forecast (the normal answer is used then).
        """
        data = await chart_service.forecast_data(question, chunks)
        if not data:
            return None

        prompt = get_prompt_template("forecast_answer.jinja2").render(
            question=question, facts=data["facts"]
        )
        text = await azure_openai_client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=settings.ANSWER_MAX_TOKENS,
        )
        text = (text or "").strip()
        if not text:
            return None

        # Numbers allowed in a forecast answer: the facts computed by the code (and the pages)
        texts = [data["facts"]] + [chunk["text"] for chunk in chunks]
        verified = self.numbers_are_in_sources(text, texts)

        numbers = []
        for value in FACT_SOURCE_RE.findall(data["facts"]):
            number = int(value)
            if 1 <= number <= len(chunks) and number not in numbers:
                numbers.append(number)

        full_answer = text + chart_block(data["chart"])
        return {
            "answer": full_answer,
            "citations": self.build_citations(numbers, chunks),
            "found": True,
            "verified": verified,
        }

    # ---------- The functions the API calls ----------

    async def answer_stream(self, question: str, chunks: list[dict]) -> AsyncIterator[dict]:
        """Yields {"type": "token"}, then one {"type": "done"} (or {"type": "error"})."""
        try:
            intent = detect_intent(question)
            logger.info(f"Intent: {intent}")

            # Forecast: code does the maths, LLM only explains it
            if intent == "forecast":
                try:
                    forecast = await self.forecast_answer(question, chunks)
                except Exception as e:
                    logger.error(f"Forecast failed, using the normal answer: {e}")
                    forecast = None
                if forecast:
                    yield {"type": "token", "text": forecast["answer"]}
                    yield {"type": "done", **forecast}
                    return
                # The report states the value itself, or there is not enough data: normal answer
                intent = "qa"

            images = await self.pick_images(question, chunks)
            messages = await self.build_messages(question, chunks, images)
            deployment = (settings.AZURE_OPENAI_VISION_DEPLOYMENT or None) if images else None
            logger.info(f"Answering with {len(chunks)} pages and {len(images)} images")

            full, sent = "", 0
            async for piece in azure_openai_client.chat_stream(
                messages, deployment=deployment, max_tokens=settings.ANSWER_MAX_TOKENS
            ):
                full += piece
                # Never send the SOURCES line (or the start of it) to the user
                marker = full.find(SOURCES_MARKER)
                safe_end = marker if marker != -1 else max(len(full) - HOLD_BACK, 0)
                if safe_end > sent:
                    yield {"type": "token", "text": full[sent:safe_end]}
                    sent = safe_end

            if not full.strip():
                logger.warning("Empty stream, trying once without streaming")
                full = await azure_openai_client.chat(
                    messages, deployment=deployment, max_tokens=settings.ANSWER_MAX_TOKENS
                )
                sent = 0
                if not full.strip():
                    yield {"type": "error", "message": ERROR_MESSAGE}
                    return

            result = self.finish(full, chunks)

            # Send what is still held back (positions are counted in the raw reply)
            marker = full.find(SOURCES_MARKER)
            raw_answer = (full if marker == -1 else full[:marker]).rstrip()
            rest = raw_answer[sent:]
            if rest:
                yield {"type": "token", "text": rest}

            # Images related to the question (only from the cited pages)
            figures = self.figure_block(question, result["answer"], chunks, result["citations"])
            if figures:
                yield {"type": "token", "text": figures}
                result["answer"] += figures

            # Comparison: the chart is added after the text answer. A chart failure never breaks the answer.
            if intent == "comparison" and result["found"]:
                try:
                    chart = await chart_service.comparison(question, chunks)
                except Exception as e:
                    logger.error(f"Comparison chart failed: {e}")
                    chart = None
                if chart:
                    block = chart_block(chart)
                    yield {"type": "token", "text": block}
                    result["answer"] += block

            yield {"type": "done", **result}
        except Exception as e:
            logger.error(f"Answer failed: {e}")
            yield {"type": "error", "message": ERROR_MESSAGE}

    async def answer(self, question: str, chunks: list[dict]) -> dict:
        """Same as answer_stream, but waits for the full answer (used by scripts/ask.py)."""
        async for event in self.answer_stream(question, chunks):
            if event["type"] == "done":
                return event
            if event["type"] == "error":
                raise RuntimeError(event["message"])
        raise RuntimeError("No answer")


answer_service = AnswerService()