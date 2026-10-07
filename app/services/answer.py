import json
import re

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.core.config import settings
from app.prompts import get_prompt_template
from app.services import forecaster, verifier
from app.services.page_store import page_store
from app.services.retriever import retriever

IMAGE_FILE_RE = re.compile(r"\s+file=\S+")


class AnswerService:
    """Retrieve, write the answer from the pages only, check it, and add projections."""

    def __init__(self):
        self.answer_prompt = get_prompt_template("answer_generation.jinja2")

    async def answer(self, question: str, history: list[dict] | None = None) -> dict:
        history = history or []
        context = await retriever.retrieve(question, history)
        pages = context["pages"]
        analysis = context["analysis"]

        if not pages:
            return self._not_found(context["question"], analysis["intent"], "No matching pages were found.")

        result = await self._generate(context, history)
        if not result:
            return self._not_found(context["question"], analysis["intent"], "The answer could not be produced.")

        # Check the answer against the pages; if something is wrong, let the model fix it
        problems = verifier.verify(result, pages)
        for attempt in range(settings.VERIFY_MAX_REPAIRS):
            if not problems:
                break
            logger.warning(f"Verification problems (repair {attempt + 1}): {problems}")
            repaired = await self._generate(context, history, feedback="\n".join(problems[:15]))
            if not repaired:
                break
            result = repaired
            problems = verifier.verify(result, pages)

        tables = result.get("tables", [])
        chart = result.get("chart")
        warnings = [f"Could not verify: {p}" for p in problems]

        # Projections are calculated in code from the verified historical numbers
        if analysis["intent"] == "forecast" and result.get("series_for_forecast"):
            f_tables, f_chart, f_warnings = forecaster.project(
                result["series_for_forecast"], analysis["forecast_periods"]
            )
            tables = tables + f_tables
            chart = f_chart or chart
            warnings += f_warnings

        return {
            "question": context["question"],
            "intent": analysis["intent"],
            "answer": result.get("answer", ""),
            "not_found": bool(result.get("not_found", False)),
            "tables": tables,
            "chart": chart,
            "citations": self._build_citations(result.get("citations", [])),
            "images": self._build_images(result.get("image_ids", []), pages),
            "warnings": warnings,
        }

    async def _generate(self, context: dict, history: list[dict], feedback: str = "") -> dict:
        pages = [
            {**p, "text": IMAGE_FILE_RE.sub("", p["text"])} for p in context["pages"]
        ]
        prompt = self.answer_prompt.render(
            question=context["question"],
            intent=context["analysis"]["intent"],
            history=history[-settings.RETRIEVAL_HISTORY_MESSAGES :],
            pages=pages,
            feedback=feedback,
        )
        reply = ""
        try:
            reply = await azure_openai_client.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=settings.ANSWER_MAX_TOKENS,
            )
            return json.loads(reply)
        except Exception as e:
            logger.error(f"Answer generation failed ({e}), raw reply: {reply[:500]!r}")
            return {}

    def _build_citations(self, citations: list[dict]) -> list[dict]:
        base = settings.PDF_BASE_URL.rstrip("/")
        out, seen = [], set()
        for c in citations:
            key = (c.get("source_pdf"), c.get("page"))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "source_pdf": c["source_pdf"],
                    "page": c["page"],
                    "evidence": c.get("evidence", ""),
                    "url": f"{base}/{c['source_pdf']}#page={c['page']}",
                }
            )
        return out

    def _build_images(self, image_ids: list[str], pages: list[dict]) -> list[dict]:
        records = page_store.images()
        prefix = settings.IMAGE_URL_PREFIX.rstrip("/")
        return [
            {
                "image_id": i,
                "url": f"{prefix}/{i}",
                "source_pdf": records[i]["source_pdf"],
                "page": records[i]["page_number"],
                "description": records[i]["description"],
            }
            for i in image_ids
            if i in records
        ]

    def _not_found(self, question: str, intent: str, reason: str) -> dict:
        return {
            "question": question,
            "intent": intent,
            "answer": reason,
            "not_found": True,
            "tables": [],
            "chart": None,
            "citations": [],
            "images": [],
            "warnings": [],
        }


answer_service = AnswerService()