import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.adapters.logger.logger import logger
from app.core.config import settings

BCRYPT_MAX_BYTES = 72

class Security:
    """Password hashing and login tokens (JWT)."""
    async def hash_password(self, password: str) -> str:
        """Turn a password into a hash that is safe to store."""
        # bcrypt is slow on purpose, so run it in a thread to keep the app responsive
        return await asyncio.to_thread(self._hash, password)

    async def verify_password(self, password: str, hashed_password: str) -> bool:
        """Check if a password matches the stored hash."""
        return await asyncio.to_thread(self._verify, password, hashed_password)

    def create_access_token(self, user_id: int) -> str:
        """Make a token that proves who the user is, for a limited time."""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {"sub": str(user_id), "exp": expire}
        return jwt.encode(
            payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

    def decode_access_token(self, token: str) -> int | None:
        """Return the user id from a valid token, or None if it is bad or expired."""
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            return int(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            return None

    def _hash(self, password: str) -> str:
        data = password.encode("utf-8")
        if len(data) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
        return bcrypt.hashpw(data, bcrypt.gensalt()).decode("utf-8")

    def _verify(self, password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except ValueError:
            # Too long or a broken hash: treat it as a wrong password
            return False


security = Security()