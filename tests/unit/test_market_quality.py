from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_market_data.contracts import NormalizedCandle
from private_trading_market_data.quality import (
    actionable_for_signals,
    detect_gaps,
    drop_out_of_order,
    is_fresh,
    validate_candle_ohlc,
)


def _c(open_time: datetime, *, o: str = "100", h: str = "110", l: str = "90", c: str = "105") -> NormalizedCandle:
    return NormalizedCandle(
        open_time=open_time,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal("1"),
        is_final=True,
        provider_symbol="BTCUSDT",
        timeframe="15m",
    )


def test_validate_candle_ohlc_flags_bad_high() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    flags = validate_candle_ohlc(_c(t0, h="95"))
    assert "high_lt_low" in flags or "high_lt_body" in flags


def test_detect_gaps_and_out_of_order() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [
        _c(t0),
        _c(t0 + timedelta(minutes=15)),
        _c(t0 + timedelta(minutes=45)),  # gap of one 15m candle
        _c(t0 + timedelta(minutes=30)),  # out of order relative to sorted insert
    ]
    ordered, dropped = drop_out_of_order(candles)
    assert dropped == 1
    gaps = detect_gaps(ordered, timeframe="15m")
    assert len(gaps) == 1


def test_freshness_and_actionable_fail_closed() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=2)
    assert is_fresh(timeframe="15m", last_open_time=last, now=now) is False
    assert actionable_for_signals(fresh=False, open_gaps=0, quality_flags=[]) is False
    assert actionable_for_signals(fresh=True, open_gaps=1, quality_flags=[]) is False
    assert actionable_for_signals(fresh=True, open_gaps=0, quality_flags=["stale"]) is False
    assert actionable_for_signals(fresh=True, open_gaps=0, quality_flags=[]) is True
