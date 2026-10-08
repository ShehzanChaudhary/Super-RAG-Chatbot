from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.adapters.logger.logger import logger
from app.core.config import settings

# Fields we read back from every search hit (the vector itself is never returned)
SELECT_FIELDS = ["source_pdf", "page_start", "page_end", "text", "image_ids"]


class AISearchClient:
    """Search on the AI Search index (the index is created by the notebook)"""

    def __init__(self):
        self.search_client = SearchClient(
            endpoint=settings.SEARCH_ENDPOINT,
            index_name=settings.SEARCH_INDEX_NAME,
            credential=AzureKeyCredential(settings.SEARCH_API_KEY),
        )

    async def search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int = 5,
        filter: str | None = None,
    ) -> list[dict]:
        """
        Hybrid search: keyword match + vector match together.
        filter example: "source_pdf eq 'Annual_Report_2023_24.pdf'"
        """
        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        hits = []
        try:
            results = await self.search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                filter=filter,
                select=SELECT_FIELDS,
                top=top_k,
            )
            async for r in results:
                hits.append(
                    {
                        "source_pdf": r["source_pdf"],
                        "page_start": r["page_start"],
                        "page_end": r["page_end"],
                        "text": r["text"],
                        "image_ids": r.get("image_ids") or [],
                        "score": r["@search.score"],
                    }
                )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

        logger.info(f"Search returned {len(hits)} results")
        return hits

    async def close(self):
        """Close the connection (called when the app shuts down)."""
        await self.search_client.close()


ai_search_client = AISearchClient()