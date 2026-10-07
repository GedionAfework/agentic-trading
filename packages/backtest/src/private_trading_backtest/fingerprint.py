from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from private_trading_features.types import CandleBar


def bar_to_dict(bar: CandleBar) -> dict[str, Any]:
    return {
        "open_time": bar.open_time.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": None if bar.volume is None else str(bar.volume),
        "is_final": bar.is_final,
    }


def bars_from_dicts(rows: list[dict[str, Any]]) -> list[CandleBar]:
    out: list[CandleBar] = []
    for row in rows:
        ot = row["open_time"]
        if isinstance(ot, str):
            ot = datetime.fromisoformat(ot.replace("Z", "+00:00"))
        out.append(
            CandleBar(
                open_time=ot,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=None if row.get("volume") is None else Decimal(str(row["volume"])),
                is_final=bool(row.get("is_final", True)),
            )
        )
    return out


def dataset_fingerprint(bars: list[CandleBar], *, symbol: str, timeframe: str) -> str:
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": [bar_to_dict(b) for b in bars],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
