"""Shared, look-ahead-safe indicators for pair specialist strategies."""

from __future__ import annotations

import math
from decimal import Decimal

from private_trading_features.atr import true_range
from private_trading_features.types import CandleBar


def ema_at(bars: list[CandleBar], index: int, period: int) -> Decimal | None:
    if index < period - 1 or index >= len(bars):
        return None
    closes = [bar.close for bar in bars[: index + 1]]
    value = sum(closes[:period], Decimal("0")) / Decimal(period)
    alpha = Decimal("2") / Decimal(period + 1)
    for close in closes[period:]:
        value = alpha * close + (Decimal("1") - alpha) * value
    return value


def atr_at(bars: list[CandleBar], index: int, period: int = 14) -> Decimal | None:
    if index < period - 1 or index >= len(bars):
        return None
    values = [
        true_range(bars[i], bars[i - 1].close if i else None)
        for i in range(index - period + 1, index + 1)
    ]
    return sum(values, Decimal("0")) / Decimal(period)


def return_pct(
    bars: list[CandleBar], index: int, lookback: int
) -> Decimal | None:
    if index < lookback or index >= len(bars):
        return None
    start = bars[index - lookback].close
    if start == 0:
        return None
    return bars[index].close / start - Decimal("1")


def relative_strength(
    bars: list[CandleBar],
    benchmark_bars: list[CandleBar],
    index: int,
    lookback: int,
) -> Decimal | None:
    """Asset return minus aligned benchmark return."""
    own = return_pct(bars, index, lookback)
    benchmark = return_pct(benchmark_bars, index, lookback)
    if own is None or benchmark is None:
        return None
    return own - benchmark


def _log_returns(
    bars: list[CandleBar], index: int, lookback: int
) -> list[float] | None:
    if index < lookback or index >= len(bars):
        return None
    returns: list[float] = []
    for i in range(index - lookback + 1, index + 1):
        previous = float(bars[i - 1].close)
        current = float(bars[i].close)
        if previous <= 0 or current <= 0:
            return None
        returns.append(math.log(current / previous))
    return returns


def rolling_beta(
    bars: list[CandleBar],
    benchmark_bars: list[CandleBar],
    index: int,
    lookback: int,
) -> Decimal | None:
    own = _log_returns(bars, index, lookback)
    bench = _log_returns(benchmark_bars, index, lookback)
    if own is None or bench is None:
        return None
    mean_bench = sum(bench) / len(bench)
    mean_own = sum(own) / len(own)
    variance = sum((value - mean_bench) ** 2 for value in bench) / len(bench)
    if variance <= 0:
        return None
    covariance = sum(
        (left - mean_own) * (right - mean_bench)
        for left, right in zip(own, bench, strict=True)
    ) / len(own)
    return Decimal(str(covariance / variance))


def beta_adjusted_return(
    bars: list[CandleBar],
    benchmark_bars: list[CandleBar],
    index: int,
    lookback: int,
) -> Decimal | None:
    """Own return minus beta times aligned benchmark return."""
    own = return_pct(bars, index, lookback)
    benchmark = return_pct(benchmark_bars, index, lookback)
    beta = rolling_beta(bars, benchmark_bars, index, lookback)
    if own is None or benchmark is None or beta is None:
        return None
    return own - beta * benchmark


def realized_volatility(
    bars: list[CandleBar], index: int, lookback: int = 24
) -> float | None:
    if index < lookback or index >= len(bars):
        return None
    returns: list[float] = []
    for i in range(index - lookback + 1, index + 1):
        previous = float(bars[i - 1].close)
        current = float(bars[i].close)
        if previous <= 0 or current <= 0:
            return None
        returns.append(math.log(current / previous))
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def volatility_ratio(
    bars: list[CandleBar],
    index: int,
    short_period: int = 14,
    long_period: int = 50,
) -> Decimal | None:
    short = atr_at(bars, index, short_period)
    long = atr_at(bars, index, long_period)
    if short is None or long is None or long == 0:
        return None
    return short / long


def rolling_extreme(
    bars: list[CandleBar],
    index: int,
    lookback: int,
    *,
    side: str,
    exclude_current: bool = True,
) -> Decimal | None:
    end = index if exclude_current else index + 1
    start = end - lookback
    if start < 0 or end > len(bars) or start >= end:
        return None
    window = bars[start:end]
    if side == "high":
        return max(bar.high for bar in window)
    if side == "low":
        return min(bar.low for bar in window)
    raise ValueError(f"unknown extreme side: {side}")


LIQUID_FOREX_SESSIONS = frozenset({"london", "overlap", "new_york_late"})


def forex_session(open_hour_utc: int) -> str:
    """Coarse UTC sessions; exact DST handling remains a data-source limitation."""
    if 7 <= open_hour_utc < 12:
        return "london"
    if 12 <= open_hour_utc < 17:
        return "overlap"
    if 17 <= open_hour_utc < 22:
        return "new_york_late"
    return "asia"


def in_liquid_forex_session(open_hour_utc: int) -> bool:
    return forex_session(open_hour_utc) in LIQUID_FOREX_SESSIONS
