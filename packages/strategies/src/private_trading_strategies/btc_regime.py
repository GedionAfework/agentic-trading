"""BTC regime tag — SHADOW ONLY. Never gates, sizes, or blocks a trade.

Rule (pre-declared, same as the 2026-10-08 walk-forward grid's "BTC regime
agreement", where it was *not* selected for SOL V1):

    latest completed BTC 4h candle:
    close > EMA12 > EMA21 > EMA50  and  EMA50 > EMA50 ten candles earlier

Purpose: tag every scan/decision with BTC's state so post-freeze paper trades
can be split into risk-on vs risk-off. Only that forward sample may justify a
future hypothesis; 2022–2026 is spent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from private_trading_features.types import CandleBar

BTC_REGIME_RULE = "btc_4h_ema_stack_slope_v1"
BTC_REGIME_SYMBOL = "BTC/USDT"
BTC_REGIME_TIMEFRAME = "4h"
SLOPE_LOOKBACK = 10
MIN_BARS = 50 + SLOPE_LOOKBACK


@dataclass(slots=True, frozen=True)
class BtcRegime:
    risk_on: bool | None  # None = not enough completed history (unknown)
    rule: str
    bar_open_time: str | None
    close: float | None
    ema12: float | None
    ema21: float | None
    ema50: float | None
    ema50_prior: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "risk_on": self.risk_on,
            "label": "unknown"
            if self.risk_on is None
            else ("risk_on" if self.risk_on else "risk_off"),
            "rule": self.rule,
            "bar_open_time": self.bar_open_time,
            "close": self.close,
            "ema12": self.ema12,
            "ema21": self.ema21,
            "ema50": self.ema50,
            "ema50_prior": self.ema50_prior,
            "shadow_only": True,
        }


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    """SMA-seeded EMA (identical to the research scripts)."""
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period]) / period
    out[period - 1] = value
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        value = values[i] * k + value * (1.0 - k)
        out[i] = value
    return out


def classify_btc_regime(btc_4h_bars: Sequence[CandleBar]) -> BtcRegime:
    """Classify on completed (final) 4h bars only. Unknown if history is short."""
    bars = [bar for bar in btc_4h_bars if bar.is_final]
    if len(bars) < MIN_BARS:
        return BtcRegime(None, BTC_REGIME_RULE, None, None, None, None, None, None)
    closes = [float(bar.close) for bar in bars]
    e12, e21, e50 = _ema(closes, 12), _ema(closes, 21), _ema(closes, 50)
    j = len(closes) - 1
    prior = e50[j - SLOPE_LOOKBACK]
    close, a, b, c = closes[j], e12[j], e21[j], e50[j]
    risk_on = (
        a is not None
        and b is not None
        and c is not None
        and prior is not None
        and close > a > b > c > prior
    )
    return BtcRegime(
        risk_on=risk_on,
        rule=BTC_REGIME_RULE,
        bar_open_time=bars[j].open_time.isoformat(),
        close=close,
        ema12=a,
        ema21=b,
        ema50=c,
        ema50_prior=prior,
    )
