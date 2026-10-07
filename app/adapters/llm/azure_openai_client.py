import base64

from openai import AsyncOpenAI
from collections.abc import AsyncIterator

from app.adapters.logger.logger import logger
from app.core.config import settings


class AzureOpenAIClient:
    """One place for all LLM calls on Azure OpenAI: chat, vision and embeddings."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/",
            timeout=60,
            max_retries=3,
        )

    async def chat(
        self,
        messages: list[dict],
        deployment: str | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """Send messages to a chat deployment and return the reply text."""
        deployment = deployment or settings.AZURE_OPENAI_CHAT_DEPLOYMENT

        extra = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        if max_tokens:
            extra["max_completion_tokens"] = max_tokens

        try:
            response = await self.client.chat.completions.create(
                model=deployment,  # in Azure, "model" means the deployment name
                messages=messages,
                **extra,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Chat call failed (deployment={deployment}): {e}")
            raise

    async def chat_stream(
        self,
        messages: list[dict],
        deployment: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Send messages to a chat deployment and yield the reply piece by piece."""
        deployment = deployment or settings.AZURE_OPENAI_CHAT_DEPLOYMENT

        extra = {}
        if max_tokens:
            extra["max_completion_tokens"] = max_tokens

        try:
            stream = await self.client.chat.completions.create(
                model=deployment,
                messages=messages,
                stream=True,
                **extra,
            )
            async for event in stream:
                # Some events have no choices (for example Azure's first event)
                if not event.choices:
                    continue
                piece = event.choices[0].delta.content
                if piece:
                    yield piece
        except Exception as e:
            logger.error(f"Chat stream failed (deployment={deployment}): {e}")
            raise

    async def vision(
        self,
        prompt: str,
        image_bytes: bytes,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """Ask the model a question about one image (a PDF page or chart)."""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        "detail": "high"
                    },
                ],
            }
        ]
        # If no separate vision deployment is set, the chat deployment is used
        deployment = (
            settings.AZURE_OPENAI_VISION_DEPLOYMENT
            or settings.AZURE_OPENAI_CHAT_DEPLOYMENT
        )
        return await self.chat(
            messages,
            deployment=deployment,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Turn a list of texts into a list of vectors (in the same order)."""
        vectors = []
        batch_size = 50

        try:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = await self.client.embeddings.create(
                    model=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                    input=batch,
                    dimensions=settings.EMBEDDING_DIMENSIONS,
                )
                vectors.extend(item.embedding for item in response.data)
        except Exception as e:
            logger.error(f"Embedding call failed: {e}")
            raise

        logger.info(f"Embedded {len(texts)} texts")
        return vectors


azure_openai_client = AzureOpenAIClient()