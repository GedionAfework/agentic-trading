from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from private_trading_db.base import Base


class MarketProvider(Base):
    __tablename__ = "market_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    symbols: Mapped[list[ProviderSymbol]] = relationship(back_populates="provider")
    candles: Mapped[list[Candle]] = relationship(back_populates="provider")


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    canonical_symbol: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    asset_class: Mapped[str] = mapped_column(String(24), nullable=False)
    base_asset: Mapped[str | None] = mapped_column(String(32))
    quote_asset: Mapped[str | None] = mapped_column(String(32))
    price_tick: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    qty_step: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    provider_symbols: Mapped[list[ProviderSymbol]] = relationship(back_populates="instrument")
    candles: Mapped[list[Candle]] = relationship(back_populates="instrument")


class ProviderSymbol(Base):
    __tablename__ = "provider_symbols"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_symbol", name="uq_provider_symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_map: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    provider: Mapped[MarketProvider] = relationship(back_populates="symbols")
    instrument: Mapped[Instrument] = relationship(back_populates="provider_symbols")


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "open_time",
            "provider_id",
            name="uq_candle_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    quality_flags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    instrument: Mapped[Instrument] = relationship(back_populates="candles")
    provider: Mapped[MarketProvider] = relationship(back_populates="candles")


class MarketDataGap(Base):
    __tablename__ = "market_data_gaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    gap_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gap_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="open")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
