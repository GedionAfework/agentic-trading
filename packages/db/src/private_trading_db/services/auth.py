from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from private_trading_core.config import Settings
from private_trading_core.errors import AppError, ForbiddenError, UnauthorizedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_db.models.identity import Session, User, UserRole
from private_trading_db.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from private_trading_db.services.audit import record_audit

GENERIC_LOGIN_ERROR = "Invalid email or password"


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: uuid.UUID
    roles: list[str]


@dataclass(slots=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str
    display_name: str | None
    roles: list[str]
    status: str


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User).options(selectinload(User.roles)).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


def _roles(user: User) -> list[str]:
    return sorted({r.role for r in user.roles})


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
    roles: list[str] | None = None,
) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        display_name=display_name,
        status="active",
    )
    session.add(user)
    await session.flush()
    for role in roles or ["owner"]:
        session.add(UserRole(user_id=user.id, role=role))
    await session.flush()
    return await get_user_by_id(session, user.id)  # type: ignore[return-value]


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings,
    device_name: str | None = None,
    ip: str | None = None,
    correlation_id: uuid.UUID | None = None,
) -> AuthTokens:
    user = await get_user_by_email(session, email)
    if user is None or user.status != "active" or not verify_password(user.password_hash, password):
        await record_audit(
            session,
            action="auth.login_failed",
            actor_type="anonymous",
            correlation_id=correlation_id,
            metadata={"email": email.lower().strip()},
        )
        await session.commit()
        raise UnauthorizedError(GENERIC_LOGIN_ERROR)

    if user.mfa_required:
        await record_audit(
            session,
            action="auth.login_mfa_required",
            actor_type="user",
            actor_id=user.id,
            correlation_id=correlation_id,
        )
        await session.commit()
        raise AppError("MFA_REQUIRED", "MFA challenge required", retryable=False)

    tokens = await _issue_tokens(
        session,
        user=user,
        settings=settings,
        device_name=device_name,
        ip=ip,
    )
    await record_audit(
        session,
        action="auth.login_succeeded",
        actor_type="user",
        actor_id=user.id,
        resource_type="session",
        correlation_id=correlation_id,
        metadata={"device_name": device_name},
    )
    await session.commit()
    return tokens


async def refresh(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings,
    correlation_id: uuid.UUID | None = None,
) -> AuthTokens:
    token_hash = hash_token(refresh_token)
    result = await session.execute(
        select(Session)
        .options(selectinload(Session.user).selectinload(User.roles))
        .where(Session.refresh_token_hash == token_hash)
    )
    current = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if current is None:
        raise UnauthorizedError("Invalid refresh token")

    if current.revoked_at is not None:
        # Refresh reuse detection: revoke the whole token family.
        await _revoke_family(session, current.token_family)
        await record_audit(
            session,
            action="auth.refresh_reuse_detected",
            actor_type="user",
            actor_id=current.user_id,
            resource_type="session",
            resource_id=current.id,
            correlation_id=correlation_id,
        )
        await session.commit()
        raise UnauthorizedError("Invalid refresh token")

    if current.expires_at <= now:
        current.revoked_at = now
        await session.commit()
        raise UnauthorizedError("Invalid refresh token")

    user = current.user
    if user.status != "active":
        raise ForbiddenError("Account is not active")

    current.revoked_at = now
    tokens = await _issue_tokens(
        session,
        user=user,
        settings=settings,
        device_name=current.device_name,
        ip=None,
        token_family=current.token_family,
    )
    await record_audit(
        session,
        action="auth.refresh_succeeded",
        actor_type="user",
        actor_id=user.id,
        resource_type="session",
        correlation_id=correlation_id,
    )
    await session.commit()
    return tokens


async def logout(
    session: AsyncSession,
    *,
    refresh_token: str | None,
    user_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None = None,
) -> None:
    now = datetime.now(UTC)
    if refresh_token:
        token_hash = hash_token(refresh_token)
        result = await session.execute(
            select(Session).where(Session.refresh_token_hash == token_hash)
        )
        row = result.scalar_one_or_none()
        if row and row.revoked_at is None:
            row.revoked_at = now
            await record_audit(
                session,
                action="auth.logout",
                actor_type="user",
                actor_id=row.user_id,
                resource_type="session",
                resource_id=row.id,
                correlation_id=correlation_id,
            )
    elif user_id:
        await record_audit(
            session,
            action="auth.logout",
            actor_type="user",
            actor_id=user_id,
            correlation_id=correlation_id,
        )
    await session.commit()


async def list_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    result = await session.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    correlation_id: uuid.UUID | None = None,
) -> None:
    result = await session.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "Session not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
    await record_audit(
        session,
        action="auth.session_revoked",
        actor_type="user",
        actor_id=user_id,
        resource_type="session",
        resource_id=session_id,
        correlation_id=correlation_id,
    )
    await session.commit()


async def _issue_tokens(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
    device_name: str | None,
    ip: str | None,
    token_family: uuid.UUID | None = None,
) -> AuthTokens:
    roles = _roles(user)
    refresh_raw = new_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
    family = token_family or uuid.uuid4()
    db_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_raw),
        token_family=family,
        device_name=device_name,
        ip_hash=_hash_ip(ip),
        expires_at=expires_at,
    )
    session.add(db_session)
    await session.flush()
    access = create_access_token(user_id=user.id, roles=roles, settings=settings)
    return AuthTokens(
        access_token=access,
        refresh_token=refresh_raw,
        token_type="bearer",
        expires_in=settings.access_token_ttl_seconds,
        user_id=user.id,
        roles=roles,
    )


async def _revoke_family(session: AsyncSession, token_family: uuid.UUID) -> None:
    now = datetime.now(UTC)
    result = await session.execute(
        select(Session).where(Session.token_family == token_family, Session.revoked_at.is_(None))
    )
    for row in result.scalars().all():
        row.revoked_at = now
