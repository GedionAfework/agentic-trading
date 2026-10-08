from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.types import CandleBar


FIXTURE_PAD = 50
FIXTURE_BOS_INDEX = FIXTURE_PAD + 10
FIXTURE_RETEST_INDEX = FIXTURE_PAD + 12


def frozen_bos_long_fixture() -> list[CandleBar]:
    """Swing high → BOS with volume → low-volume retest of the broken level.

    Pad is long enough for EMA50. Safer-entry playbook fires on the retest bar.
    """
    base = datetime(2024, 1, 1, tzinfo=UTC)
    raw: list[tuple[str, str, str, str, str]] = []
    for _i in range(FIXTURE_PAD):
        raw.append(("100", "101", "99", "100", "100"))

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
        ("124", "126", "123", "125", "80"),
        ("125", "125", "119", "120.5", "40"),  # low-volume retest of 120
        ("120.5", "128", "120", "126", "90"),
        ("126", "132", "125", "131", "100"),
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
