"""One-time Telegram link challenge. The web session mints a code; the bot consumes it once."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from private_trading_db.models.identity import TelegramAccount
from private_trading_db.models.telegram import TelegramLinkChallenge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity
CODE_LENGTH = 8


def generate_link_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def hash_link_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def challenge_is_valid(
    *, expires_at: datetime, consumed_at: datetime | None, now: datetime | None = None
) -> bool:
    current = now or datetime.now(UTC)
    return consumed_at is None and expires_at > current


def deep_link(bot_username: str, code: str) -> str | None:
    if not bot_username:
        return None
    return f"https://t.me/{bot_username.lstrip('@')}?start={code}"


async def create_link_challenge(
    session: AsyncSession, *, user_id: uuid.UUID, ttl_seconds: int
) -> tuple[str, TelegramLinkChallenge]:
    code = generate_link_code()
    challenge = TelegramLinkChallenge(
        user_id=user_id,
        code_hash=hash_link_code(code),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(challenge)
    await session.flush()
    return code, challenge


async def consume_link_challenge(
    session: AsyncSession,
    *,
    code: str,
    telegram_user_id: int,
    telegram_chat_id: int,
    username: str | None,
    now: datetime | None = None,
) -> TelegramAccount | None:
    """Returns the linked account, or None when the code is unknown / expired / already used."""
    current = now or datetime.now(UTC)
    result = await session.execute(
        select(TelegramLinkChallenge).where(TelegramLinkChallenge.code_hash == hash_link_code(code))
    )
    challenge = result.scalar_one_or_none()
    if challenge is None or not challenge_is_valid(
        expires_at=challenge.expires_at, consumed_at=challenge.consumed_at, now=current
    ):
        return None
    challenge.consumed_at = current
    challenge.consumed_by_telegram_user_id = telegram_user_id

    existing = await session.execute(
        select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
    )
    account = existing.scalar_one_or_none()
    if account is None:
        account = TelegramAccount(
            user_id=challenge.user_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
        )
        session.add(account)
    else:
        account.user_id = challenge.user_id
        account.telegram_chat_id = telegram_chat_id
        account.username = username
        account.revoked_at = None
        account.linked_at = current
    await session.flush()
    return account


async def find_linked_account(
    session: AsyncSession, *, telegram_user_id: int
) -> TelegramAccount | None:
    result = await session.execute(
        select(TelegramAccount).where(
            TelegramAccount.telegram_user_id == telegram_user_id,
            TelegramAccount.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def list_linked_chats(session: AsyncSession, *, user_id: uuid.UUID) -> list[TelegramAccount]:
    result = await session.execute(
        select(TelegramAccount).where(
            TelegramAccount.user_id == user_id, TelegramAccount.revoked_at.is_(None)
        )
    )
    return list(result.scalars().all())


async def revoke_account(
    session: AsyncSession, *, account_id: uuid.UUID, user_id: uuid.UUID
) -> TelegramAccount | None:
    result = await session.execute(
        select(TelegramAccount).where(
            TelegramAccount.id == account_id, TelegramAccount.user_id == user_id
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        return None
    account.revoked_at = datetime.now(UTC)
    await session.flush()
    return account
