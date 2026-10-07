from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from private_trading_db.base import Base


class ScreenshotJob(Base):
    """Chart screenshot analysis. Vision is evidence, never trade authority."""

    __tablename__ = "screenshot_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="analyzed")
    market_symbol: Mapped[str | None] = mapped_column(String(40))
    market_timeframe: Mapped[str | None] = mapped_column(String(20))
    extraction: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    verification: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    authorizes_trade: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    corrected_symbol: Mapped[str | None] = mapped_column(String(40))
    corrected_timeframe: Mapped[str | None] = mapped_column(String(20))
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
