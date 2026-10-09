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
    
    """OpenRouter (LLM)"""
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    CHAT_MODEL: str = "openai/gpt-4o-mini"      # answers, routing, rewriting
    VISION_MODEL: str = "openai/gpt-4o"         # reads charts/tables at ingestion
    EMBEDDING_MODEL: str = "openai/text-embedding-3-large"
    
    """AI Search (Vector Store)"""
    SEARCH_ENDPOINT: str = ""
    SEARCH_API_KEY: str = ""
    SEARCH_INDEX_NAME: str = "rag-assistant-bot"

    """Retrieval"""
    PAGES_DIR: Path = PROJECT_ROOT / "output" / "pages"
    METADATA_DIR: Path = PROJECT_ROOT / "output" / "metadata"
    RETRIEVAL_CHUNKS_PER_QUERY: int = 5
    RETRIEVAL_PAGES_PER_REPORT: int = 4
    RETRIEVAL_PAGES_FOCUS_REPORT: int = 6
    EMBEDDING_DIMENSIONS:int = 3072
    RETRIEVAL_HISTORY_MESSAGES: int = 6
    REWRITE_MAX_TOKENS: int = 4000

    REPORT_FILES: list[str] = [
    "Annual_Report_2021_22_1.pdf",
    "Annual_Report_2022_23.pdf",
    "Annual_Report_2023_24.pdf",
    ]
    RETRIEVAL_PER_REPORT_K: int = 4

    """Answer"""
    ANSWER_MAX_TOKENS: int = 6000
    DOCUMENTS_URL: str = "/api/documents"

    """Database"""
    DATABASE_URL: str = "sqlite+aiosqlite:///./rag_bot.db"

    """Auth"""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    """CORS (browser origins allowed to call this API)"""
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    """Azure OpenAI"""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = ""       
    AZURE_OPENAI_VISION_DEPLOYMENT: str = ""     
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore"
    )

settings = Settings()