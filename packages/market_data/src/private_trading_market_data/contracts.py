from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}

# Fail-closed freshness: last closed candle older than this (seconds) is stale.
FRESHNESS_MAX_AGE_SECONDS: dict[str, int] = {
    "1m": 3 * 60,
    "5m": 12 * 60,
    "15m": 40 * 60,
    "1h": 3 * 60 * 60,
    "4h": 10 * 60 * 60,
    "1d": 36 * 60 * 60,
}


@dataclass(slots=True, frozen=True)
class NormalizedCandle:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    is_final: bool
    provider_symbol: str
    timeframe: str


@dataclass(slots=True, frozen=True)
class InstrumentInfo:
    canonical_symbol: str
    asset_class: str
    base_asset: str
    quote_asset: str
    provider_symbol: str
    price_tick: Decimal | None = None
    qty_step: Decimal | None = None


@dataclass(slots=True)
class MarketSnapshot:
    instrument_symbol: str
    timeframe: str
    as_of: datetime
    last_open_time: datetime | None
    last_close: Decimal | None
    candle_count: int
    fresh: bool
    actionable: bool
    quality_flags: list[str] = field(default_factory=list)
    gaps_open: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderHealth:
    provider_code: str
    ok: bool
    latency_ms: float | None = None
    message: str = ""
    degraded: bool = False
