from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from private_trading_features.types import CandleBar


def bars_from_rows(rows: list[dict[str, Any]]) -> list[CandleBar]:
    """Build CandleBar list from plain dict fixtures (tests / notebooks)."""
    out: list[CandleBar] = []
    for row in rows:
        open_time = row["open_time"]
        if isinstance(open_time, str):
            open_time = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
        out.append(
            CandleBar(
                open_time=open_time,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=None if row.get("volume") is None else Decimal(str(row["volume"])),
                is_final=bool(row.get("is_final", True)),
            )
        )
    return out


def from_normalized(candles: list[Any]) -> list[CandleBar]:
    """Adapt market_data NormalizedCandle (duck-typed) → CandleBar."""
    return [
        CandleBar(
            open_time=c.open_time,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            is_final=getattr(c, "is_final", True),
        )
        for c in candles
    ]
