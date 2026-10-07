import asyncio
import json
import re

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.core.config import settings
from app.prompts import get_prompt_template
from app.services.page_store import page_store

# "2023-24" or "2023/24": a financial year written as a range
YEAR_RANGE_RE = re.compile(r"(?<!\d)(20\d{2})\s*[-–/]\s*(\d{2})(?!\d)")
# "2024" or "FY2024": a single year
YEAR_RE = re.compile(r"(?<!\d)20\d{2}(?!\d)")

INTENTS = {"lookup", "comparison", "forecast", "chart_or_image", "other"}


class Retriever:
    """Understands the question, finds the right chunks, and loads their exact pages."""

    def __init__(self):
        self.analysis_prompt = get_prompt_template("query_analysis.jinja2")

    async def analyze_question(self, question: str, history: list[dict]) -> dict:
        """Resolve follow-ups ('ok 2026') and detect what kind of answer is needed."""
        fallback = {
            "standalone_question": question,
            "intent": "lookup",
            "sub_queries": [],
            "forecast_periods": [],
        }
        recent = history[-settings.RETRIEVAL_HISTORY_MESSAGES :]
        prompt = self.analysis_prompt.render(history=recent, question=question)

        reply = ""
        try:
            reply = await azure_openai_client.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=settings.REWRITE_MAX_TOKENS,
            )
            logger.info(f"Analysis raw reply: {reply!r}")
            data = json.loads(reply)
        except Exception as e:
            # If analysis fails, search with the original question instead of crashing
            logger.error(f"Question analysis failed ({e}), raw reply: {reply!r}")
            return fallback

        standalone = (data.get("standalone_question") or "").strip() or question
        intent = data.get("intent") if data.get("intent") in INTENTS else "lookup"
        sub_queries = [q.strip() for q in data.get("sub_queries", []) if isinstance(q, str) and q.strip()]
        periods = []
        for p in data.get("forecast_periods", []):
            try:
                periods.append(int(p))
            except (TypeError, ValueError):
                continue

        logger.info(f"Analysis: '{question}' -> '{standalone}' intent={intent} subs={sub_queries}")
        return {
            "standalone_question": standalone,
            "intent": intent,
            "sub_queries": sub_queries,
            "forecast_periods": periods,
        }

    async def retrieve(self, question: str, history: list[dict] | None = None) -> dict:
        """Analyze the question, search the matching reports, and load the exact pages."""
        analysis = await self.analyze_question(question, history or [])
        standalone = analysis["standalone_question"]

        # The full question first, then one short query per year/metric (comparison, forecast)
        queries = [standalone]
        queries += [q for q in analysis["sub_queries"] if q != standalone]
        queries = queries[: settings.RETRIEVAL_MAX_QUERIES]

        vectors = await azure_openai_client.embed(queries)

        # One search per (query, report), all at the same time
        searches = []
        for i, (query, vector) in enumerate(zip(queries, vectors)):
            top_k = settings.RETRIEVAL_PER_REPORT_K if i == 0 else settings.RETRIEVAL_SUBQUERY_K
            for pdf_name in self._pick_reports(query):
                searches.append(
                    ai_search_client.search(
                        query,
                        vector,
                        top_k=top_k,
                        filter=f"source_pdf eq '{pdf_name}'",
                    )
                )
        logger.info(f"Running {len(searches)} searches for {len(queries)} queries")

        raw = await asyncio.gather(*searches, return_exceptions=True)
        results = [r for r in raw if not isinstance(r, Exception)]
        for r in raw:
            if isinstance(r, Exception):
                logger.error(f"A search failed: {r}")
        if not results:
            raise RuntimeError("All searches failed")

        chunks = self._merge(results)
        pages = self._load_pages(chunks)
        logger.info(f"Retrieved {len(chunks)} chunks -> {len(pages)} pages for: {standalone}")
        return {
            "question": standalone,
            "analysis": analysis,
            "chunks": chunks,
            "pages": pages,
        }

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
        """Join all search results (best hit of every list first) and remove duplicates."""
        seen = set()
        merged = []
        longest = max((len(hits) for hits in result_lists), default=0)
        for rank in range(longest):
            for hits in result_lists:
                if rank >= len(hits):
                    continue
                hit = hits[rank]
                key = (hit["source_pdf"], hit["page_start"], hit["page_end"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
        return merged

    def _load_pages(self, chunks: list[dict]) -> list[dict]:
        """Turn the retrieved chunks into the exact pages they cover, best chunk first."""
        pages = []
        seen = set()
        for chunk in chunks:
            for number in range(chunk["page_start"], chunk["page_end"] + 1):
                key = (chunk["source_pdf"], number)
                if key in seen:
                    continue
                text = page_store.get_page(chunk["source_pdf"], number)
                if text is None:
                    continue
                seen.add(key)
                pages.append({"source_pdf": chunk["source_pdf"], "page": number, "text": text})
                if len(pages) >= settings.ANSWER_MAX_CONTEXT_PAGES:
                    return pages
        return pages


retriever = Retriever()