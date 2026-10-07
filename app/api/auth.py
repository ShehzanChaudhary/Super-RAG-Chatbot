from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.database import database
from app.adapters.logger.logger import logger
from app.core.security import security
from app.models.models import User
from app.repositories.user_repository import user_repository
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# auto_error=False: we raise our own 401, so every auth failure looks the same
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(database.get_session),
) -> User:
    """Read the token from the header and return the logged-in user."""
    if credentials is None:
        raise unauthorized("Not logged in")

    user_id = security.decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized("Invalid or expired token")

    user = await user_repository.get_by_id(session, user_id)
    if user is None:
        raise unauthorized("User no longer exists")

    return user


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    session: AsyncSession = Depends(database.get_session),
):
    """Create a new account."""
    existing = await user_repository.get_by_email(session, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered",
        )

    hashed_password = await security.hash_password(body.password)

    try:
        user = await user_repository.create(session, body.email, hashed_password)
    except IntegrityError:
        # Two signups with the same email at the same moment: the database stopped one
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered",
        )

    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(database.get_session),
):
    """Check email and password, and give back a token."""
    user = await user_repository.get_by_email(session, body.email)

    # Same message for "no such email" and "wrong password", so nobody can
    # find out which emails are registered
    if user is None or not await security.verify_password(
        body.password, user.hashed_password
    ):
        logger.warning(f"Failed login for: {body.email}")
        raise unauthorized("Incorrect email or password")

    token = security.create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Who am I? The frontend uses this to check if the saved token still works."""
    return current_user