import re
from collections.abc import AsyncIterator
from urllib.parse import quote

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.core.config import settings
from app.prompts import get_prompt_template

NOT_FOUND_MESSAGE = "Ye jawab mujhe reports me nahi mila."
ERROR_MESSAGE = "Jawab banate waqt error aaya. Dobara try karo."
MARKER = "SOURCES:"


class AnswerService:
    """Builds the final answer from retrieved chunks, streams it, and adds citations."""

    def __init__(self):
        self.answer_prompt = get_prompt_template("answer.jinja2")

    async def answer_stream(self, question: str, chunks: list[dict]) -> AsyncIterator[dict]:
        """
        Yield events:
          {"type": "token", "text": "..."}   a piece of the answer, show it right away
          {"type": "done", "found", "verified", "answer", "citations"}   the last event
          {"type": "error", "message": "..."}   something broke
        """
        # Nothing retrieved: do not call the LLM at all
        if not chunks:
            yield {"type": "token", "text": NOT_FOUND_MESSAGE}
            yield self._done(False, True, NOT_FOUND_MESSAGE, [])
            return

        prompt = self.answer_prompt.render(question=question, chunks=chunks)

        buffer = ""  # everything the LLM wrote so far
        sent = 0     # how many characters of the buffer the user has already got

        try:
            async for piece in azure_openai_client.chat_stream(
                [{"role": "user", "content": prompt}],
                max_tokens=settings.ANSWER_MAX_TOKENS,
            ):
                buffer += piece
                safe = self._safe_length(buffer)
                if safe > sent:
                    yield {"type": "token", "text": buffer[sent:safe]}
                    sent = safe
        except Exception as e:
            logger.error(f"Answer stream failed: {e}")
            yield {"type": "error", "message": ERROR_MESSAGE}
            return

        answer_text, sources_text, marker_index = self._split_sources(buffer)

        if marker_index != -1 and sent > marker_index:
            logger.warning("The SOURCES line was shown to the user")

        # LLM wrote nothing before the SOURCES line
        if not answer_text:
            logger.warning(f"Empty answer from LLM, raw buffer: {buffer!r}")
            yield {"type": "token", "text": NOT_FOUND_MESSAGE}
            yield self._done(False, True, NOT_FOUND_MESSAGE, [])
            return

        # No SOURCES line at all: the answer cannot be verified
        if sources_text is None:
            logger.warning("Answer had no SOURCES line")
            yield self._done(True, False, answer_text, [])
            return

        # LLM says the answer is not in the reports
        if sources_text.strip().lower() == "none":
            logger.info("LLM said the answer is not in the sources")
            yield self._done(False, True, answer_text, [])
            return

        numbers = [int(n) for n in re.findall(r"\d+", sources_text)]
        citations = self._build_citations(numbers, chunks)

        # Answer shown, but none of its sources is valid
        if not citations:
            logger.warning(f"Answer had no valid sources: {sources_text}")
            yield self._done(True, False, answer_text, [])
            return

        yield self._done(True, True, answer_text, citations)

    async def answer(self, question: str, chunks: list[dict]) -> dict:
        """Same as answer_stream, but waits and returns only the final result."""
        async for event in self.answer_stream(question, chunks):
            if event["type"] == "done":
                return event
            if event["type"] == "error":
                break
        return self._done(False, False, NOT_FOUND_MESSAGE, [])

    def _safe_length(self, buffer: str) -> int:
        """How many characters at the start of the buffer are safe to show the user."""
        # The SOURCES marker always starts a new line, so only the current
        # (last) line can be the marker. Hold it back while it still looks like one.
        line_start = buffer.rfind("\n") + 1
        current_line = buffer[line_start:].lstrip()
        if MARKER.startswith(current_line) or current_line.startswith(MARKER):
            return line_start
        return len(buffer)

    def _split_sources(self, full_text: str) -> tuple[str, str | None, int]:
        """Split the reply into (answer, text after SOURCES:, marker position)."""
        index = full_text.rfind(MARKER)
        if index == -1:
            return full_text.strip(), None, -1
        answer = full_text[:index].strip()
        sources = full_text[index + len(MARKER):].strip()
        return answer, sources, index

    def _build_citations(self, source_numbers: list, chunks: list[dict]) -> list[dict]:
        """Convert the source numbers from the LLM into clickable citations."""
        citations = []
        seen = set()

        for number in source_numbers:
            # Source numbers start at 1, so chunk index = number - 1
            if not isinstance(number, int) or not 1 <= number <= len(chunks):
                logger.warning(f"Ignoring invalid source number: {number}")
                continue

            chunk = chunks[number - 1]
            key = (chunk["source_pdf"], chunk["page_start"], chunk["page_end"])
            if key in seen:
                continue
            seen.add(key)

            citations.append(
                {
                    "doc_name": chunk["source_pdf"],
                    "pdf_page": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "url": (
                        f"{settings.DOCUMENTS_URL}/{quote(chunk['source_pdf'])}"
                        f"#page={chunk['page_start']}"
                    ),
                }
            )

        return citations

    def _done(self, found: bool, verified: bool, answer: str, citations: list[dict]) -> dict:
        return {
            "type": "done",
            "found": found,
            "verified": verified,
            "answer": answer,
            "citations": citations,
        }


answer_service = AnswerService()