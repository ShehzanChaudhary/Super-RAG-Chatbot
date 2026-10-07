from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.db.database import database
from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.api import auth, chat, documents
from app.core.config import settings

# Imported only so that Base knows the tables before create_tables() runs
from app.models import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the app starts, and once when it stops."""
    logger.info("App starting")
    await database.create_tables()

    yield  # the app runs here

    logger.info("App stopping")
    await ai_search_client.close()
    await database.close()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)