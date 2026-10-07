from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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


class ScanRun(Base):
    """One scanner evaluation of a closed candle. Unique per candle so reruns are no-ops."""

    __tablename__ = "scan_runs"
    __table_args__ = (
        UniqueConstraint(
            "instrument_symbol", "timeframe", "candle_open_time", name="uq_scan_run_candle"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    instrument_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    candle_open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str | None] = mapped_column(String(20))
    setup_state: Mapped[str | None] = mapped_column(String(40))
    fresh: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    candidate_new: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class SignalCandidate(Base):
    """Deduplicated setup candidate. Same anchor on later candles updates, never re-alerts."""

    __tablename__ = "signal_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    strategy_code: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    setup_anchor: Mapped[str] = mapped_column(String(80), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    candle_open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    publish_state: Mapped[str] = mapped_column(String(32), nullable=False)
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
