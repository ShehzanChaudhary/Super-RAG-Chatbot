from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from app.adapters.logger.logger import logger
from app.core.config import settings

# Fields we read back from every search hit (the vector itself is never returned)
SELECT_FIELDS = ["source_pdf", "page_start", "page_end", "text", "image_ids"]


class AISearchClient:
    """Everything related to the AI Search Index"""

    def __init__(self):
        self.settings = settings
        credential = AzureKeyCredential(self.settings.SEARCH_API_KEY)

        # Used to create/delete the index
        self.index_client = SearchIndexClient(
            endpoint=self.settings.SEARCH_ENDPOINT,
            credential=credential,
        )

        # Used to upload and search documents
        self.search_client = SearchClient(
            endpoint=self.settings.SEARCH_ENDPOINT,
            index_name=self.settings.SEARCH_INDEX_NAME,
            credential=credential,
        )

    async def create_index(self):
        """Creates the index (or updates it if it already exists). Same schema as the notebook."""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="source_pdf", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="page_start", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="page_end", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SearchableField(name="text", type=SearchFieldDataType.String),
            SimpleField(
                name="image_ids",
                type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                filterable=True,
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.settings.EMBEDDING_DIMENSIONS,
                vector_search_profile_name="default-vector-profile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
            profiles=[
                VectorSearchProfile(
                    name="default-vector-profile",
                    algorithm_configuration_name="default-hnsw",
                )
            ],
        )

        index = SearchIndex(
            name=self.settings.SEARCH_INDEX_NAME,
            fields=fields,
            vector_search=vector_search,
        )

        try:
            await self.index_client.create_or_update_index(index)
            logger.info(f"Index ready : {self.settings.SEARCH_INDEX_NAME}")
        except Exception as e:
            logger.error(f"Could not create index: {e}")
            raise

    async def delete_index(self):
        """Delete the index"""
        try:
            await self.index_client.delete_index(self.settings.SEARCH_INDEX_NAME)
            logger.info(f"Index deleted: {self.settings.SEARCH_INDEX_NAME}")
        except Exception as e:
            logger.error(f"Could not delete index: {e}")
            raise

    async def upload_chunks(self, chunks: list[dict]):
        """
        Upload chunks to the index.
        Each chunk is a dict with: id, source_pdf, page_start, page_end,
        text, image_ids, content_vector.
        """
        batch_size = 100
        uploaded = 0

        try:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                results = await self.search_client.upload_documents(documents=batch)
                uploaded += sum(1 for r in results if r.succeeded)
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise

        logger.info(f"Uploaded {uploaded} of {len(chunks)} chunks")

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
        """Close connections (call this when the app shuts down)."""
        await self.search_client.close()
        await self.index_client.close()


ai_search_client = AISearchClient()