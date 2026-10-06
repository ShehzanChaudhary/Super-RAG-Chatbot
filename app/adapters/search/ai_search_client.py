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
    VectorSearchProfile
)
from azure.search.documents.models import VectorizedQuery

from app.adapters.logger import logger
from app.core.config import settings

class AISearchClient:
    """Everything related to the AI Search Index"""

    def __init__(self):
        self.settings = settings
        credential = AzureKeyCredential(self.settings.SEARCH_API_KEY)

        """Use to create/delete the index"""
        self.index_client = SearchIndexClient(
            endpoint=self.settings.SEARCH_ENDPOINT,
            credential=credential
        )

        """Use to upload and search documents"""
        self.search_client = SearchClient(
            endpoint=self.settings.SEARCH_ENDPOINT,
            index_name=self.settings.SEARCH_INDEX_NAME,
            credential=credential        
        )

    async def create_index(self):
        """Creates the index (or update it if already exists)"""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.settings.EMBEDDING_DIMENSIONS,
                vector_search_profile_name="vector-profile",
                stored=False,
            ),
            SimpleField(name="doc_name", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="report_year", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="pdf_page", type=SearchFieldDataType.Int32, filterable=True),
            SimpleField(name="chunk_type", type=SearchFieldDataType.String, filterable=True),
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[
                VectorSearchProfile(
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config"
                )
            ]
        )

        index = SearchIndex(
            name=self.settings.SEARCH_INDEX_NAME,
            fields=fields,
            vector_search=vector_search
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
        Each chunk is a dict with: id, content, content_vector,
        doc_name, report_year, pdf_page, chunk_type.
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
        filter example: "report_year eq 'FY2024' and chunk_type eq 'table'"
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
                top=top_k,
            )
            async for r in results:
                hits.append(
                    {
                        "content": r["content"],
                        "doc_name": r["doc_name"],
                        "report_year": r["report_year"],
                        "pdf_page": r["pdf_page"],
                        "chunk_type": r["chunk_type"],
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