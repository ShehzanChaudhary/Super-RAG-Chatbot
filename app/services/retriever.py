import asyncio
import json

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.core.config import settings
from app.prompts import get_prompt_template


class Retriever:
    """Rewrites follow-up questions and finds the best chunks for them."""

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
                max_tokens=200,
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
        """Rewrite the question, then search text, table and chart chunks."""
        standalone = await self.rewrite_question(question, history or [])

        vectors = await azure_openai_client.embed([standalone])
        query_vector = vectors[0]

        # Three searches at the same time: all chunks, only tables, only charts
        results = await asyncio.gather(
            ai_search_client.search(
                standalone, query_vector, top_k=settings.RETRIEVAL_TOP_K
            ),
            ai_search_client.search(
                standalone,
                query_vector,
                top_k=settings.RETRIEVAL_TABLE_K,
                filter="chunk_type eq 'table'",
            ),
            ai_search_client.search(
                standalone,
                query_vector,
                top_k=settings.RETRIEVAL_CHART_K,
                filter="chunk_type eq 'chart'",
            ),
        )

        chunks = self._merge(results)
        logger.info(f"Retrieved {len(chunks)} unique chunks for: {standalone}")
        return {"question": standalone, "chunks": chunks}

    def _merge(self, result_lists: list[list[dict]]) -> list[dict]:
        """Join all search results into one list and remove duplicates."""
        seen = set()
        merged = []
        for hits in result_lists:
            for hit in hits:
                key = (hit["doc_name"], hit["pdf_page"], hit["content"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
        return merged


retriever = Retriever()