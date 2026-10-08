"""Michael's EMA 12/21/50 — from owner TradingView screenshots (advisory HTF proxy)."""

from __future__ import annotations

from decimal import Decimal

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.types import CandleBar, FeatureValue, TriState

EMA_VERSION = "1.0.0-ec"
EMA_PERIODS = (12, 21, 50)


def _ema_at(closes: list[Decimal], period: int) -> Decimal | None:
    if len(closes) < period:
        return None
    seed = sum(closes[:period], Decimal("0")) / Decimal(period)
    k = Decimal("2") / Decimal(period + 1)
    ema = seed
    one = Decimal("1")
    for price in closes[period:]:
        ema = price * k + ema * (one - k)
    return ema


def _compute_ema(bars: list[CandleBar], index: int, *, period: int) -> FeatureValue:
    name = f"ema_{period}"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, EMA_VERSION, "index_out_of_range")
    if not bars[index].is_final:
        return FeatureValue.unknown(name, EMA_VERSION, "bar_not_final")
    closes = [b.close for b in bars[: index + 1]]
    value = _ema_at(closes, period)
    if value is None:
        return FeatureValue.unknown(
            name, EMA_VERSION, "insufficient_bars", required=period, available=index + 1
        )
    return FeatureValue.of(
        name,
        EMA_VERSION,
        status=TriState.TRUE,
        value=value,
        period=period,
        definition_id="EMA-012-021-050",
        lock_status="engineering_candidate",
    )


def compute_ema_12(bars: list[CandleBar], index: int) -> FeatureValue:
    return _compute_ema(bars, index, period=12)


def compute_ema_21(bars: list[CandleBar], index: int) -> FeatureValue:
    return _compute_ema(bars, index, period=21)


def compute_ema_50(bars: list[CandleBar], index: int) -> FeatureValue:
    return _compute_ema(bars, index, period=50)


def compute_ema_htf_bias(bars: list[CandleBar], index: int) -> FeatureValue:
    """Long if close above EMA50, short if below. Matches screenshot HTF filter."""
    name = "ema_htf_bias"
    ema50 = compute_ema_50(bars, index)
    if ema50.status != TriState.TRUE or ema50.value is None:
        return FeatureValue.unknown(name, EMA_VERSION, ema50.reason or "ema50_unknown")
    close = bars[index].close
    if close > ema50.value:
        bias = "long"
    elif close < ema50.value:
        bias = "short"
    else:
        return FeatureValue.of(
            name,
            EMA_VERSION,
            status=TriState.FALSE,
            value=None,
            reason="close_equals_ema50",
            ema_50=ema50.value,
            definition_id="EMA-012-021-050",
            lock_status="engineering_candidate",
        )
    return FeatureValue.of(
        name,
        EMA_VERSION,
        status=TriState.TRUE,
        value=bias,
        ema_50=ema50.value,
        close=close,
        definition_id="EMA-012-021-050",
        lock_status="engineering_candidate",
    )


for _period, _fn in ((12, compute_ema_12), (21, compute_ema_21), (50, compute_ema_50)):
    register(
        FeatureSpec(
            name=f"ema_{_period}",
            version=EMA_VERSION,
            lookback=_period,
            description=f"EMA({_period}) close (Michael's EMA stack)",
            lock_status="engineering_candidate",
            definition_id="EMA-012-021-050",
            compute=_fn,
        )
    )

register(
    FeatureSpec(
        name="ema_htf_bias",
        version=EMA_VERSION,
        lookback=50,
        description="HTF bias from close vs EMA50",
        lock_status="engineering_candidate",
        definition_id="EMA-012-021-050",
        dependencies=("ema_50",),
        compute=compute_ema_htf_bias,
    )
)
