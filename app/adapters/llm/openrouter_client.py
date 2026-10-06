import base64
from openai import AsyncOpenAI

from app.adapters.logger import logger
from app.core.config import settings

class OpenRouterClient:
    """Makes all LLM calls: chat, vision, and embeddings"""

    def __init__(self):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=self.settings.OPENROUTER_API_KEY,
            base_url=self.settings.OPENROUTER_BASE_URL,
            timeout=60,
            max_retries=3,
        )

    async def chat(self, messages: list[dict], model: str | None = None, tempreature: float = 0.0, json_mode: bool = False) -> str:
        """Send messages to the chat model and return the reply text"""
        model = model or self.settings.CHAT_MODEL

        extra = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=tempreature,
                **extra
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Chat call failed (model={model}): {e}")
            raise

    async def vision(self, prompt: str, image_bytes: bytes, json_mode: bool = False) -> str:
        """Ask the vision model a question about one image (a PDF page or chart)"""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ]
        return await self.chat(
            messages,
            model=self.settings.VISION_MODEL,
            json_mode=json_mode
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Turn a list of texts into a list of vectors (in the same order)."""
        vectors = []
        batch_size = 50

        try:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = await self.client.embeddings.create(
                    model=self.settings.EMBEDDING_MODEL,
                    input=batch,
                )
                vectors.extend(item.embedding for item in response.data)
        except Exception as e:
            logger.error(f"Embedding call failed: {e}")
            raise

        logger.info(f"Embedded {len(texts)} texts")
        return vectors

openrouter_client = OpenRouterClient()

    
