from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState


def _bar(
    i: int,
    *,
    o: str,
    h: str,
    l: str,
    c: str,
    v: str = "100",
    start: datetime | None = None,
) -> CandleBar:
    base = start or datetime(2026, 1, 1, tzinfo=UTC)
    return CandleBar(
        open_time=base + timedelta(hours=i),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal(v),
        is_final=True,
    )


def test_atr_unknown_with_short_history() -> None:
    bars = [_bar(i, o="100", h="101", l="99", c="100") for i in range(5)]
    result = compute_feature("atr", bars, len(bars) - 1)
    assert result.status == TriState.UNKNOWN
    assert result.reason == "insufficient_bars"


def test_atr_known_after_lookback() -> None:
    bars = [_bar(i, o="100", h="102", l="98", c="100") for i in range(20)]
    result = compute_feature("atr", bars, 19)
    assert result.status == TriState.TRUE
    assert result.value is not None
    assert result.value > 0


def test_volume_significant_and_low() -> None:
    bars = [_bar(i, o="100", h="101", l="99", c="100", v="100") for i in range(25)]
    # Spike volume on last bar
    bars[-1] = _bar(24, o="100", h="101", l="99", c="100", v="300")
    sig = compute_feature("significant_volume", bars, 24)
    assert sig.status == TriState.TRUE
    assert sig.value is True

    bars[-1] = _bar(24, o="100", h="101", l="99", c="100", v="50")
    low = compute_feature("low_volume", bars, 24)
    assert low.status == TriState.TRUE
    assert low.value is True


def test_missing_volume_is_unknown_not_pass() -> None:
    bars = [_bar(i, o="100", h="101", l="99", c="100") for i in range(25)]
    bars[-1] = CandleBar(
        open_time=bars[-1].open_time,
        open=bars[-1].open,
        high=bars[-1].high,
        low=bars[-1].low,
        close=bars[-1].close,
        volume=None,
        is_final=True,
    )
    result = compute_feature("significant_volume", bars, 24)
    assert result.status == TriState.UNKNOWN


def test_no_lookahead_window_truncation() -> None:
    """Features must not see bars after the evaluation index."""
    bars = [_bar(i, o="100", h="101", l="99", c="100") for i in range(30)]
    # If look-ahead leaked, a future spike would change ATR at index 20.
    early = compute_feature("atr", bars, 20)
    bars[25] = _bar(25, o="100", h="200", l="50", c="100")
    late = compute_feature("atr", bars, 20)
    assert early.value == late.value
