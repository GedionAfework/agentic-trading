from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import ForbiddenError, UnauthorizedError
from private_trading_db.security import decode_access_token
from private_trading_db.services.auth import get_user_by_id
from private_trading_db.session import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: str | None
    roles: list[str]
    status: str

    def require_roles(self, *allowed: str) -> None:
        if not any(role in self.roles for role in allowed):
            raise ForbiddenError("Insufficient permissions")


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_db_session():
        yield session


def get_correlation_id(request: Request) -> uuid.UUID | None:
    raw = getattr(request.state, "correlation_id", None)
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing access token")
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid access token")
    user_id = uuid.UUID(str(payload["sub"]))
    user = await get_user_by_id(session, user_id)
    if user is None or user.status != "active":
        raise UnauthorizedError("Invalid access token")
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=sorted({r.role for r in user.roles}),
        status=user.status,
    )


def client_ip(
    request: Request,
    x_forwarded_for: Annotated[str | None, Header(alias="X-Forwarded-For")] = None,
) -> str | None:
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
