from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.audit import record_audit_event
from app.config import Settings
from app.database import get_db_session
from app.models import ActorType, Membership, User
from app.schemas import (
    BusinessSummary,
    LoginRequest,
    SessionProfile,
    TokenResponse,
    UserSummary,
)
from app.security import AuthContext, create_access_token, get_auth_context, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> TokenResponse:
    membership = session.scalar(
        select(Membership)
        .join(User)
        .options(joinedload(Membership.user), joinedload(Membership.business))
        .where(User.email == payload.email.lower())
    )
    if membership is None or not verify_password(
        payload.password, membership.user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password tidak cocok.",
        )

    user = membership.user

    settings: Settings = request.app.state.settings
    token, expires_in = create_access_token(
        user_id=user.id,
        business_id=membership.business_id,
        settings=settings,
    )
    record_audit_event(
        session,
        business_id=membership.business_id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        action="auth.login.succeeded",
        entity_type="user",
        entity_id=user.id,
        correlation_id=request.state.correlation_id,
        metadata={"role": membership.role.value},
    )
    session.commit()

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserSummary.model_validate(user),
        business=BusinessSummary.model_validate(membership.business),
        role=membership.role,
    )


@router.get("/me", response_model=SessionProfile)
def me(context: Annotated[AuthContext, Depends(get_auth_context)]) -> SessionProfile:
    return SessionProfile(
        user=UserSummary.model_validate(context.user),
        business=BusinessSummary.model_validate(context.business),
        role=context.membership.role,
    )
