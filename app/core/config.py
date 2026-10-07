from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.adapters.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """App"""
    APP_NAME: str = "RAG Assistant Bot"
    DEBUG: bool = False

    """Paths"""
    PDF_DIR: Path = PROJECT_ROOT / "docs"
    DATA_DIR: Path = PROJECT_ROOT / "data"

    """OpenRouter (LLM)"""
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    CHAT_MODEL: str = "openai/gpt-4o-mini"      # answers, routing, rewriting
    VISION_MODEL: str = "openai/gpt-4o"         # reads charts/tables at ingestion
    EMBEDDING_MODEL: str = "openai/text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 1536

    """AI Search (Vector Store)"""
    SEARCH_ENDPOINT: str = ""
    SEARCH_API_KEY: str = ""
    SEARCH_INDEX_NAME: str = "rag-assistant-bot"

    """Retrieval"""
    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_TABLE_K: int = 4
    RETRIEVAL_CHART_K: int = 3
    RETRIEVAL_HISTORY_MESSAGES: int = 6

    """Answer"""
    ANSWER_MAX_TOKENS: int = 1500
    DOCUMENTS_URL: str = "/api/documents"

    """Database"""
    DATABASE_URL: str = "sqlite+aiosqlite:///./rag_bot.db"

    """Auth"""
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    """CORS (browser origins allowed to call this API)"""
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    """Azure OpenAI"""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = ""       # your gpt-4.1-mini deployment name
    AZURE_OPENAI_VISION_DEPLOYMENT: str = ""     # empty = use the chat deployment
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore"
    )

settings = Settings()