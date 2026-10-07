import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.database import database
from app.adapters.logger.logger import logger
from app.api.auth import get_current_user
from app.models.models import Chat, User
from app.repositories.chat_repository import chat_repository
from app.schemas.chat import (
    AskRequest,
    ChatDetailResponse,
    ChatResponse,
    MessageResponse,
)
from app.services.answer import answer_service
from app.services.retriever import retriever

router = APIRouter(prefix="/api/chats", tags=["chats"])

ERROR_MESSAGE = "Jawab banate waqt error aaya. Dobara try karo."


def sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def get_chat_or_404(session: AsyncSession, chat_id: int, user_id: int) -> Chat:
    """Find the chat of this user, or raise 404."""
    chat = await chat_repository.get_chat(session, chat_id, user_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


async def save_answer(chat_id: int, user_id: int, event: dict) -> int | None:
    """Save the bot's answer. Uses its own session, because the request session
    may already be closed when the stream ends."""
    try:
        async with database.session_factory() as session:
            chat = await chat_repository.get_chat(session, chat_id, user_id)
            if chat is None:
                return None
            message = await chat_repository.add_message(
                session, chat, "assistant", event["answer"], event["citations"]
            )
            return message.id
    except Exception as e:
        logger.error(f"Could not save the answer: {e}")
        return None


async def stream_answer(
    chat_id: int, user_id: int, title: str, question: str, history: list[dict]
) -> AsyncIterator[str]:
    """Search, answer, and send the answer to the browser piece by piece."""
    try:
        result = await retriever.retrieve(question, history)
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        yield sse("error", {"message": ERROR_MESSAGE})
        return

    async for event in answer_service.answer_stream(result["question"], result["chunks"]):
        if event["type"] == "token":
            yield sse("token", {"text": event["text"]})

        elif event["type"] == "error":
            yield sse("error", {"message": event["message"]})
            return

        elif event["type"] == "done":
            message_id = await save_answer(chat_id, user_id, event)
            yield sse(
                "done",
                {
                    "chat_id": chat_id,
                    "title": title,
                    "message_id": message_id,
                    "found": event["found"],
                    "verified": event["verified"],
                    "citations": event["citations"],
                },
            )


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
):
    """Start a new empty chat."""
    return await chat_repository.create_chat(session, current_user.id)


@router.get("", response_model=list[ChatResponse])
async def list_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
):
    """All chats of the user, latest first. This is the sidebar."""
    return await chat_repository.list_chats(session, current_user.id)


@router.get("/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
):
    """One chat with all its messages."""
    chat = await get_chat_or_404(session, chat_id, current_user.id)
    messages = await chat_repository.get_messages(session, chat.id)
    return ChatDetailResponse(
        chat=ChatResponse.model_validate(chat),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post("/{chat_id}/ask")
async def ask(
    chat_id: int,
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
):
    """Ask a question in a chat. The answer comes back as a stream of events."""
    chat = await get_chat_or_404(session, chat_id, current_user.id)

    # History is read BEFORE the new question is saved
    messages = await chat_repository.get_messages(session, chat.id)
    history = [{"role": m.role, "content": m.content} for m in messages]

    # This also sets the chat title if this is the first question
    await chat_repository.add_message(session, chat, "user", body.question)

    return StreamingResponse(
        stream_answer(chat.id, current_user.id, chat.title, body.question, history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )