from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from private_trading_db.base import Base


class PaperAccount(Base):
    """Simulated account. Always labeled PAPER — never live money."""

    __tablename__ = "paper_accounts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "label", name="uq_paper_account_owner_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PAPER")
    currency: Mapped[str] = mapped_column(String(12), nullable=False, server_default="USDT")
    starting_equity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fill_model: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    soak_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    soak_days_required: Mapped[int] = mapped_column(Integer, nullable=False, server_default="14")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PaperTrade(Base):
    """Lifecycle: ready → open → closed (or cancelled while ready)."""

    __tablename__ = "paper_trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    instrument_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PAPER")
    signal_bar_open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_entry: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    stop_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    target_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    invalidation_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    qty: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    risk_amount: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fill_model: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    entry_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    entry_bar_open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    exit_bar_open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(String(60))
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 8))
    realized_r: Mapped[float | None] = mapped_column(Numeric(12, 6))
    costs: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    bars_held: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperTradeEvent(Base):
    """Append-only lifecycle log for integrity / soak audits."""

    __tablename__ = "paper_trade_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    bar_open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JournalEntry(Base):
    """Auto-journal row created when a paper trade closes. Cohort = paper (never mixed)."""

    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_trade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trades.id", ondelete="SET NULL"),
        unique=True,
    )
    cohort: Mapped[str] = mapped_column(String(20), nullable=False, server_default="paper")
    instrument_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    realized_r: Mapped[float | None] = mapped_column(Numeric(12, 6))
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 8))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
