from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from private_trading_db.base import Base


class TelegramLinkChallenge(Base):
    """One-time code issued from the authenticated web session. Only the hash is stored."""

    __tablename__ = "telegram_link_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TelegramUpdate(Base):
    """Inbound webhook/polling update. Unique update_id makes processing idempotent."""

    __tablename__ = "telegram_updates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    linked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    handled: Mapped[str] = mapped_column(String(60), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationDelivery(Base):
    """One alert message to one chat. Unique per (candidate, chat) so re-dispatch never repeats."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("candidate_id", "telegram_chat_id", name="uq_delivery_candidate_chat"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="telegram")
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_markup: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    transport: Mapped[str | None] = mapped_column(String(20))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramAlertAction(Base):
    """Owner response to an alert button: viewed / why / dismissed / decision_taken / skipped."""

    __tablename__ = "telegram_alert_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
