from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.types import CandleBar


def frozen_bos_long_fixture() -> list[CandleBar]:
    """Deterministic synthetic series with a confirmable swing high then bullish BOS.

    Used for regression — fingerprint must remain stable.
    """
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # Pad with enough bars for ATR(14) and volume SMA(20)
    raw: list[tuple[str, str, str, str, str]] = []
    for i in range(25):
        # quiet base
        raw.append(("100", "101", "99", "100", "100"))

    # Build swing high around index 29 (after pad 0..24)
    # indices 25-35 crafted like Phase 6 golden series
    crafted = [
        ("100", "105", "99", "102", "100"),
        ("102", "108", "101", "106", "100"),
        ("106", "110", "104", "108", "100"),
        ("108", "115", "107", "112", "100"),
        ("112", "120", "111", "118", "100"),  # swing high candidate
        ("118", "119", "110", "111", "100"),
        ("111", "112", "105", "106", "100"),
        ("106", "108", "100", "102", "90"),
        ("102", "104", "98", "100", "80"),
        ("100", "103", "97", "101", "85"),
        ("101", "125", "100", "124", "250"),  # BOS close 124 > 120 + significant volume
        # follow-through for entry next open / exit paths
        ("124", "126", "123", "125", "120"),
        ("125", "128", "118", "119", "110"),  # dips toward stop zone
        ("119", "130", "118", "129", "140"),  # push to target area
        ("129", "132", "128", "131", "100"),
    ]
    raw.extend(crafted)

    bars: list[CandleBar] = []
    for i, (o, h, l, c, v) in enumerate(raw):
        bars.append(
            CandleBar(
                open_time=base + timedelta(hours=i),
                open=Decimal(o),
                high=Decimal(h),
                low=Decimal(l),
                close=Decimal(c),
                volume=Decimal(v),
                is_final=True,
            )
        )
    return bars


FIXTURE_CODE = "frozen_bos_long_v1"
FIXTURE_SYMBOL = "BTC/USDT"
FIXTURE_TIMEFRAME = "1h"
