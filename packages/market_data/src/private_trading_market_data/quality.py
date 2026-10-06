from __future__ import annotations

from datetime import UTC, datetime, timedelta

from private_trading_market_data.contracts import (
    FRESHNESS_MAX_AGE_SECONDS,
    TIMEFRAME_SECONDS,
    NormalizedCandle,
)


def validate_candle_ohlc(candle: NormalizedCandle) -> list[str]:
    flags: list[str] = []
    if candle.high < candle.low:
        flags.append("high_lt_low")
    if candle.high < max(candle.open, candle.close):
        flags.append("high_lt_body")
    if candle.low > min(candle.open, candle.close):
        flags.append("low_gt_body")
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        flags.append("non_positive_price")
    return flags


def detect_gaps(
    candles: list[NormalizedCandle],
    *,
    timeframe: str,
) -> list[tuple[datetime, datetime]]:
    step = TIMEFRAME_SECONDS.get(timeframe)
    if not step or len(candles) < 2:
        return []
    expected = timedelta(seconds=step)
    gaps: list[tuple[datetime, datetime]] = []
    ordered = sorted(candles, key=lambda c: c.open_time)
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        delta = cur.open_time - prev.open_time
        if delta > expected:
            gaps.append((prev.open_time + expected, cur.open_time))
    return gaps


def drop_out_of_order(candles: list[NormalizedCandle]) -> tuple[list[NormalizedCandle], int]:
    """Keep strictly increasing open_time; count discarded out-of-order rows."""
    kept: list[NormalizedCandle] = []
    dropped = 0
    last: datetime | None = None
    for candle in candles:
        if last is not None and candle.open_time <= last:
            dropped += 1
            continue
        kept.append(candle)
        last = candle.open_time
    return kept, dropped


def is_fresh(
    *,
    timeframe: str,
    last_open_time: datetime | None,
    now: datetime | None = None,
) -> bool:
    if last_open_time is None:
        return False
    max_age = FRESHNESS_MAX_AGE_SECONDS.get(timeframe)
    step = TIMEFRAME_SECONDS.get(timeframe)
    if max_age is None or step is None:
        return False
    current = now or datetime.now(UTC)
    if last_open_time.tzinfo is None:
        last_open_time = last_open_time.replace(tzinfo=UTC)
    # Age measured from candle close (open + timeframe)
    close_time = last_open_time + timedelta(seconds=step)
    age = (current - close_time).total_seconds()
    return age <= max_age


def actionable_for_signals(
    *,
    fresh: bool,
    open_gaps: int,
    quality_flags: list[str],
) -> bool:
    blocking = {"high_lt_low", "non_positive_price", "provider_degraded", "stale"}
    if not fresh:
        return False
    if open_gaps > 0:
        return False
    return not any(flag in blocking for flag in quality_flags)
