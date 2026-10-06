from __future__ import annotations

from decimal import Decimal

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.types import CandleBar, FeatureValue, TriState

VOLUME_VERSION = "1.0.0-ec"
VOLUME_SMA_PERIOD = 20
# Engineering candidates — not course-locked (VOL-001 / VOL-002).
T_SIG = Decimal("1.5")
T_LOW = Decimal("0.7")


def _volume_at(bars: list[CandleBar], index: int) -> Decimal | None:
    vol = bars[index].volume
    if vol is None:
        return None
    return vol


def compute_volume_sma(
    bars: list[CandleBar], index: int, *, period: int = VOLUME_SMA_PERIOD
) -> FeatureValue:
    name = "volume_sma"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, VOLUME_VERSION, "index_out_of_range")
    if index + 1 < period:
        return FeatureValue.unknown(
            name, VOLUME_VERSION, "insufficient_bars", required=period, available=index + 1
        )
    vals: list[Decimal] = []
    for i in range(index - period + 1, index + 1):
        v = _volume_at(bars, i)
        if v is None:
            return FeatureValue.unknown(name, VOLUME_VERSION, "missing_volume", at_index=i)
        vals.append(v)
    sma = sum(vals, Decimal("0")) / Decimal(period)
    return FeatureValue.of(
        name,
        VOLUME_VERSION,
        status=TriState.TRUE,
        value=sma,
        period=period,
        definition_id="VOL-003",
        lock_status="engineering_candidate",
    )


def compute_volume_ratio(
    bars: list[CandleBar], index: int, *, period: int = VOLUME_SMA_PERIOD
) -> FeatureValue:
    name = "volume_ratio"
    sma = compute_volume_sma(bars, index, period=period)
    if sma.status == TriState.UNKNOWN or sma.value is None:
        return FeatureValue.unknown(name, VOLUME_VERSION, sma.reason or "sma_unknown")
    vol = _volume_at(bars, index)
    if vol is None:
        return FeatureValue.unknown(name, VOLUME_VERSION, "missing_volume")
    if sma.value == 0:
        return FeatureValue.unknown(name, VOLUME_VERSION, "sma_zero")
    ratio = vol / sma.value
    return FeatureValue.of(
        name,
        VOLUME_VERSION,
        status=TriState.TRUE,
        value=ratio,
        volume=vol,
        sma=sma.value,
        definition_id="VOL-001",
        lock_status="engineering_candidate",
    )


def compute_significant_volume(
    bars: list[CandleBar],
    index: int,
    *,
    period: int = VOLUME_SMA_PERIOD,
    t_sig: Decimal = T_SIG,
) -> FeatureValue:
    name = "significant_volume"
    ratio = compute_volume_ratio(bars, index, period=period)
    if ratio.status == TriState.UNKNOWN or ratio.value is None:
        return FeatureValue.unknown(name, VOLUME_VERSION, ratio.reason or "ratio_unknown")
    ok = ratio.value >= t_sig
    return FeatureValue.of(
        name,
        VOLUME_VERSION,
        status=TriState.TRUE if ok else TriState.FALSE,
        value=ok,
        ratio=ratio.value,
        threshold=t_sig,
        definition_id="VOL-001",
        lock_status="engineering_candidate",
    )


def compute_low_volume(
    bars: list[CandleBar],
    index: int,
    *,
    period: int = VOLUME_SMA_PERIOD,
    t_low: Decimal = T_LOW,
) -> FeatureValue:
    name = "low_volume"
    ratio = compute_volume_ratio(bars, index, period=period)
    if ratio.status == TriState.UNKNOWN or ratio.value is None:
        return FeatureValue.unknown(name, VOLUME_VERSION, ratio.reason or "ratio_unknown")
    ok = ratio.value <= t_low
    return FeatureValue.of(
        name,
        VOLUME_VERSION,
        status=TriState.TRUE if ok else TriState.FALSE,
        value=ok,
        ratio=ratio.value,
        threshold=t_low,
        definition_id="VOL-002",
        lock_status="engineering_candidate",
    )


register(
    FeatureSpec(
        name="volume_sma",
        version=VOLUME_VERSION,
        lookback=VOLUME_SMA_PERIOD,
        description=f"SMA(volume, {VOLUME_SMA_PERIOD})",
        lock_status="engineering_candidate",
        definition_id="VOL-003",
        compute=compute_volume_sma,
    )
)
register(
    FeatureSpec(
        name="volume_ratio",
        version=VOLUME_VERSION,
        lookback=VOLUME_SMA_PERIOD,
        description="candle_volume / volume_sma",
        lock_status="engineering_candidate",
        definition_id="VOL-001",
        dependencies=("volume_sma",),
        compute=compute_volume_ratio,
    )
)
register(
    FeatureSpec(
        name="significant_volume",
        version=VOLUME_VERSION,
        lookback=VOLUME_SMA_PERIOD,
        description=f"volume_ratio >= {T_SIG} (VOL-001 EC)",
        lock_status="engineering_candidate",
        definition_id="VOL-001",
        dependencies=("volume_ratio",),
        compute=compute_significant_volume,
    )
)
register(
    FeatureSpec(
        name="low_volume",
        version=VOLUME_VERSION,
        lookback=VOLUME_SMA_PERIOD,
        description=f"volume_ratio <= {T_LOW} (VOL-002 EC)",
        lock_status="engineering_candidate",
        definition_id="VOL-002",
        dependencies=("volume_ratio",),
        compute=compute_low_volume,
    )
)
