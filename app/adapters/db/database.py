from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.adapters.logger.logger import logger
from app.core.config import settings


class Base(DeclarativeBase):
    """Every table model (User, Chat, Message) inherits from this."""
    pass


class Database:
    """Everything related to the SQL database."""

    def __init__(self):
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
        )
        # expire_on_commit=False: objects stay readable after commit
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    async def create_tables(self):
        """Create all tables that do not exist yet."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables ready")
        except Exception as e:
            logger.error(f"Could not create tables: {e}")
            raise

    async def get_session(self):
        """FastAPI dependency: gives one session per request, closes it after."""
        async with self.session_factory() as session:
            yield session

    async def close(self):
        """Close connections (call this when the app shuts down)."""
        await self.engine.dispose()


database = Database()