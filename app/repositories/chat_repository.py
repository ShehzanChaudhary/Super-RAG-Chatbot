from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.logger.logger import logger
from app.models.models import Chat, Message, utc_now

DEFAULT_TITLE = "New chat"
TITLE_LENGTH = 50


class ChatRepository:
    """All database work related to chats and messages."""

    async def create_chat(self, session: AsyncSession, user_id: int) -> Chat:
        """Create an empty chat for a user."""
        chat = Chat(user_id=user_id, title=DEFAULT_TITLE)
        session.add(chat)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Could not create chat: {e}")
            raise

        return chat

    async def list_chats(self, session: AsyncSession, user_id: int) -> list[Chat]:
        """All chats of one user, latest first (this is the sidebar list)."""
        result = await session.execute(
            select(Chat)
            .where(Chat.user_id == user_id)
            .order_by(Chat.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_chat(
        self, session: AsyncSession, chat_id: int, user_id: int
    ) -> Chat | None:
        """Find a chat, but only if it belongs to this user."""
        result = await session.execute(
            select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_messages(self, session: AsyncSession, chat_id: int) -> list[Message]:
        """All messages of one chat, oldest first."""
        result = await session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        session: AsyncSession,
        chat: Chat,
        role: str,
        content: str,
        citations: list[dict] | None = None,
    ) -> Message:
        """Save one message and move the chat to the top of the sidebar."""
        message = Message(
            chat_id=chat.id,
            role=role,
            content=content,
            citations=citations,
        )
        session.add(message)

        # The first user question becomes the chat title
        if role == "user" and chat.title == DEFAULT_TITLE:
            chat.title = content.strip()[:TITLE_LENGTH]

        chat.updated_at = utc_now()

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Could not save message: {e}")
            raise

        return message


chat_repository = ChatRepository()