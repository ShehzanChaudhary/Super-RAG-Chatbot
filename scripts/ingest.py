import asyncio

from app.adapters.search.ai_search_client import ai_search_client
from app.services.ingestion import ingestion_service

async def main():
    try:
        await ingestion_service.ingest_all(reset=True)
    finally:
        await ai_search_client.close()


asyncio.run(main())