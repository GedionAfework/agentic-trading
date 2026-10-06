from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.engine import compute_feature, compute_snapshot
from private_trading_features.swings import confirmed_swings
from private_trading_features.types import CandleBar, TriState


def _series() -> list[CandleBar]:
    """Golden-ish pattern: base → swing high → pullback → bullish BOS close.

    Indices (1h bars). Swing radius=2 so a high at j needs bars j-2..j+2.
    """
    base = datetime(2026, 2, 1, tzinfo=UTC)
    # prices crafted so index 4 is unique swing high at 120,
    # then later close above 120 at index 10.
    raw = [
        # 0-2 left of swing
        (100, 105, 99, 102, "100"),
        (102, 108, 101, 106, "100"),
        (106, 110, 104, 108, "100"),
        (108, 115, 107, 112, "100"),
        (112, 120, 111, 118, "100"),  # 4 candidate swing high
        (118, 119, 110, 111, "100"),  # 5
        (111, 112, 105, 106, "100"),  # 6 right side lower highs
        (106, 108, 100, 102, "90"),  # 7
        (102, 104, 98, 100, "80"),  # 8
        (100, 103, 97, 101, "85"),  # 9
        (101, 125, 100, 124, "250"),  # 10 close 124 > swing 120 + sig volume later
    ]
    bars: list[CandleBar] = []
    for i, (o, h, l, c, v) in enumerate(raw):
        bars.append(
            CandleBar(
                open_time=base + timedelta(hours=i),
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
                volume=Decimal(v),
                is_final=True,
            )
        )
    return bars


def test_swing_high_confirmed_without_lookahead() -> None:
    bars = _series()
    # At index 5, swing at 4 not yet confirmed (needs +2)
    early = confirmed_swings(bars, as_of_index=5)
    assert not any(s.kind == "high" and s.index == 4 for s in early)
    # At index 6, swing high at 4 is confirmable
    later = confirmed_swings(bars, as_of_index=6)
    highs = [s for s in later if s.kind == "high" and s.index == 4]
    assert len(highs) == 1
    assert highs[0].price == Decimal("120")


def test_bos_bullish_golden() -> None:
    bars = _series()
    # Before break
    pre = compute_feature("bos_bullish", bars, 9)
    assert pre.status in {TriState.TRUE, TriState.FALSE}
    assert pre.value is False
    # Break bar
    bos = compute_feature("bos_bullish", bars, 10)
    assert bos.status == TriState.TRUE
    assert bos.value is True
    assert bos.meta["swing_price"] == Decimal("120")


def test_snapshot_cache_key_stable() -> None:
    bars = _series()
    a = compute_snapshot(bars, 10, ["bos_bullish", "last_swing_high"])
    b = compute_snapshot(bars, 10, ["bos_bullish", "last_swing_high"])
    assert a.cache_key == b.cache_key
    assert a.values["bos_bullish"].status == TriState.TRUE
