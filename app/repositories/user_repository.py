from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.logger.logger import logger
from app.models.models import User


class UserRepository:
    """All database work related to users."""

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:
        """Find a user by email. Returns None if there is no such user."""
        result = await session.execute(
            select(User).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, session: AsyncSession, user_id: int) -> User | None:
        """Find a user by id. Returns None if there is no such user."""
        return await session.get(User, user_id)

    async def create(
        self, session: AsyncSession, email: str, hashed_password: str
    ) -> User:
        """Save a new user. The password must already be hashed."""
        user = User(
            email=email.strip().lower(),
            hashed_password=hashed_password,
        )
        session.add(user)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Could not create user: {e}")
            raise

        logger.info(f"User created: {user.email}")
        return user


user_repository = UserRepository()