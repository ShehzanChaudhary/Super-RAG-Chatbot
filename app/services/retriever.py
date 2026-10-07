import asyncio
import json
import re

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.core.config import settings
from app.prompts import get_prompt_template

# "2023-24" or "2023/24": a financial year written as a range
YEAR_RANGE_RE = re.compile(r"(?<!\d)(20\d{2})\s*[-–/]\s*(\d{2})(?!\d)")
# "2024" or "FY2024": a single year
YEAR_RE = re.compile(r"(?<!\d)20\d{2}(?!\d)")


class Retriever:
    """Rewrites follow-up questions and finds the best chunks from the right reports."""

    def __init__(self):
        self.rewrite_prompt = get_prompt_template("query_rewrite.jinja2")

    async def rewrite_question(self, question: str, history: list[dict]) -> str:
        """Turn a follow-up like 'ok 2026' into a complete standalone question."""
        # First question of a chat: nothing to rewrite, so skip the LLM call
        if not history:
            return question

        recent = history[-settings.RETRIEVAL_HISTORY_MESSAGES :]
        prompt = self.rewrite_prompt.render(history=recent, question=question)

        reply = ""
        try:
            reply = await azure_openai_client.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=settings.REWRITE_MAX_TOKENS,
            )
            logger.info(f"Rewrite raw reply: {reply!r}")
            standalone = json.loads(reply).get("standalone_question", "").strip()
        except Exception as e:
            # If rewrite fails, search with the original question instead of crashing
            logger.error(f"Question rewrite failed ({e}), raw reply: {reply!r}")
            return question

        if not standalone:
            return question

        logger.info(f"Rewrote question: '{question}' -> '{standalone}'")
        return standalone

    async def retrieve(self, question: str, history: list[dict] | None = None) -> dict:
        """Rewrite the question, then search only the reports that match its years."""
        standalone = await self.rewrite_question(question, history or [])

        vectors = await azure_openai_client.embed([standalone])
        query_vector = vectors[0]

        reports = self._pick_reports(standalone)
        logger.info(f"Searching reports: {reports}")

        # One search per report, all at the same time
        results = await asyncio.gather(
            *[
                ai_search_client.search(
                    standalone,
                    query_vector,
                    top_k=settings.RETRIEVAL_PER_REPORT_K,
                    filter=f"source_pdf eq '{pdf_name}'",
                )
                for pdf_name in reports
            ]
        )

        chunks = self._merge(results)
        logger.info(f"Retrieved {len(chunks)} unique chunks for: {standalone}")
        return {"question": standalone, "chunks": chunks}

    def _find_years(self, question: str) -> set[int]:
        """Financial years (as the ending year) mentioned in the question."""
        years = set()
        # "2023-24" means FY2024
        for start, end in YEAR_RANGE_RE.findall(question):
            years.add(int(start[:2] + end))
        # take the ranges out first, so "2023-24" is not also read as 2023
        rest = YEAR_RANGE_RE.sub(" ", question)
        for year in YEAR_RE.findall(rest):
            years.add(int(year))
        return years

    def _pick_reports(self, question: str) -> list[str]:
        """Choose which report files to search, based on the years in the question."""
        years = self._find_years(question)
        if not years:
            return settings.REPORT_FILES

        wanted = set()
        for year in years:
            # The report of that year, and the next year's report
            # (it repeats the previous year's numbers as comparison)
            for fy in (year, year + 1):
                tag = f"{fy - 1}_{str(fy)[2:]}"  # FY2024 -> "2023_24"
                wanted.update(f for f in settings.REPORT_FILES if tag in f)

        # Years with no report (for example a forecast year): search everything
        if not wanted:
            return settings.REPORT_FILES

        # keep the same order as REPORT_FILES
        return [f for f in settings.REPORT_FILES if f in wanted]

    def _merge(self, result_lists: list[list[dict]]) -> list[dict]:
        """Join all search results into one list and remove duplicates."""
        seen = set()
        merged = []
        for hits in result_lists:
            for hit in hits:
                key = (hit["source_pdf"], hit["page_start"], hit["page_end"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
        return merged


retriever = Retriever()