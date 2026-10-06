from __future__ import annotations

from decimal import Decimal

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.types import CandleBar, FeatureValue, TriState

ATR_VERSION = "1.0.0"
ATR_PERIOD = 14


def true_range(bar: CandleBar, prev_close: Decimal | None) -> Decimal:
    high_low = bar.high - bar.low
    if prev_close is None:
        return high_low
    return max(high_low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def compute_atr(bars: list[CandleBar], index: int, *, period: int = ATR_PERIOD) -> FeatureValue:
    name = "atr"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, ATR_VERSION, "index_out_of_range")
    if index + 1 < period:
        return FeatureValue.unknown(
            name, ATR_VERSION, "insufficient_bars", required=period, available=index + 1
        )

    trs: list[Decimal] = []
    for i in range(index - period + 1, index + 1):
        prev = bars[i - 1].close if i > 0 else None
        trs.append(true_range(bars[i], prev))
    atr = sum(trs, Decimal("0")) / Decimal(period)
    return FeatureValue.of(
        name,
        ATR_VERSION,
        status=TriState.TRUE,
        value=atr,
        period=period,
        lock_status="engineering_candidate",
    )


def compute_range_vs_atr(
    bars: list[CandleBar], index: int, *, period: int = ATR_PERIOD
) -> FeatureValue:
    name = "range_vs_atr"
    atr = compute_atr(bars, index, period=period)
    if atr.status == TriState.UNKNOWN or atr.value is None:
        return FeatureValue.unknown(name, ATR_VERSION, atr.reason or "atr_unknown")
    bar = bars[index]
    rng = bar.high - bar.low
    if atr.value == 0:
        return FeatureValue.unknown(name, ATR_VERSION, "atr_zero")
    ratio = rng / atr.value
    return FeatureValue.of(
        name,
        ATR_VERSION,
        status=TriState.TRUE,
        value=ratio,
        range=rng,
        atr=atr.value,
        definition_id="RNG-001",
        lock_status="engineering_candidate",
    )


register(
    FeatureSpec(
        name="atr",
        version=ATR_VERSION,
        lookback=ATR_PERIOD,
        description=f"Average True Range({ATR_PERIOD})",
        lock_status="engineering_candidate",
        definition_id="RNG-001",
        compute=compute_atr,
    )
)
register(
    FeatureSpec(
        name="range_vs_atr",
        version=ATR_VERSION,
        lookback=ATR_PERIOD,
        description="Bar range / ATR(period)",
        lock_status="engineering_candidate",
        definition_id="RNG-001",
        dependencies=("atr",),
        compute=compute_range_vs_atr,
    )
)
