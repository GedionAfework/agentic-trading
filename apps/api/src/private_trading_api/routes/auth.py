from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import UnauthorizedError
from private_trading_db.services import auth as auth_service
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import (
    CurrentUser,
    bearer_scheme,
    client_ip,
    get_correlation_id,
    get_current_user,
    get_db,
)
from private_trading_api.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    SessionOut,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser | None:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, session, settings)
    except UnauthorizedError:
        return None


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    tokens = await auth_service.login(
        session,
        email=str(body.email),
        password=body.password,
        settings=settings,
        device_name=body.device_name,
        ip=client_ip(request),
        correlation_id=get_correlation_id(request),
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=tokens.user_id,
        roles=tokens.roles,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    tokens = await auth_service.refresh(
        session,
        refresh_token=body.refresh_token,
        settings=settings,
        correlation_id=get_correlation_id(request),
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=tokens.user_id,
        roles=tokens.roles,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> None:
    await auth_service.logout(
        session,
        refresh_token=body.refresh_token,
        user_id=user.id if user else None,
        correlation_id=get_correlation_id(request),
    )


@router.get("/me", response_model=MeResponse)
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=user.roles,
        status=user.status,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[SessionOut]:
    rows = await auth_service.list_sessions(session, user.id)
    return [
        SessionOut(
            id=row.id,
            device_name=row.device_name,
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            current=False,
        )
        for row in rows
    ]


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    await auth_service.revoke_session(
        session,
        user_id=user.id,
        session_id=session_id,
        correlation_id=get_correlation_id(request),
    )
