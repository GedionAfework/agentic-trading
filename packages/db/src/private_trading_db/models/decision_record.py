from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from private_trading_db.base import Base


class DecisionRecord(Base):
    """Final recommendation snapshot. Numeric fields are copied from deterministic engines."""

    __tablename__ = "decision_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    bar_open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    setup_state: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_code: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    stop_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    target_price: Mapped[float | None] = mapped_column(Numeric(20, 8))
    rr_ratio: Mapped[float | None] = mapped_column(Numeric(12, 6))
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    model_score: Mapped[float | None] = mapped_column(Numeric(8, 6))
    model_band: Mapped[str | None] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_source: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    workflow: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    hard_blockers: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
