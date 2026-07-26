import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.database import get_db_session
from app.models import Business, Membership, User

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    business: Business
    membership: Membership

    @property
    def business_id(self) -> uuid.UUID:
        return self.business.id


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def create_access_token(
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    settings: Settings,
) -> tuple[str, int]:
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "bid": str(business_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "iss": "umkm-finance-autopilot",
    }
    return (
        jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm),
        expires_in,
    )


def get_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AuthContext:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token akses diperlukan.",
        )

    settings: Settings = request.app.state.settings
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="umkm-finance-autopilot",
        )
        user_id = uuid.UUID(payload["sub"])
        business_id = uuid.UUID(payload["bid"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token akses tidak valid atau sudah kedaluwarsa.",
        ) from exc

    membership = session.scalar(
        select(Membership)
        .options(joinedload(Membership.user), joinedload(Membership.business))
        .where(
            Membership.user_id == user_id,
            Membership.business_id == business_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses bisnis tidak ditemukan.",
        )

    return AuthContext(
        user=membership.user,
        business=membership.business,
        membership=membership,
    )
