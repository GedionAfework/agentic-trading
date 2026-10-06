from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    id: uuid.UUID
    canonical_symbol: str
    asset_class: str
    base_asset: str | None
    quote_asset: str | None
    enabled: bool


class CandleOut(BaseModel):
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    is_final: bool
    quality_flags: list[str] = Field(default_factory=list)


class SyncRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=64)
    timeframe: str = Field(default="15m", min_length=2, max_length=12)
    limit: int = Field(default=200, ge=1, le=1000)


class SyncResponse(BaseModel):
    instrument_symbol: str
    timeframe: str
    upserted: int
    gaps_detected: int
    dropped_out_of_order: int
    quality_flag_counts: dict[str, int]


class MarketSnapshotOut(BaseModel):
    instrument_symbol: str
    timeframe: str
    as_of: datetime
    last_open_time: datetime | None
    last_close: Decimal | None
    candle_count: int
    fresh: bool
    actionable: bool
    quality_flags: list[str]
    gaps_open: int


class ProviderHealthOut(BaseModel):
    provider_code: str
    ok: bool
    latency_ms: float | None = None
    message: str = ""
    degraded: bool = False
