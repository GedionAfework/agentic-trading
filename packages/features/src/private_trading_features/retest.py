"""Demand/supply retest after BOS — owner charts enter the zone, not the impulse bar."""

from __future__ import annotations

from decimal import Decimal

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.structure import _bos
from private_trading_features.swings import last_swing
from private_trading_features.types import CandleBar, FeatureValue, TriState
from private_trading_features.volume import compute_low_volume, compute_significant_volume

RETEST_VERSION = "1.0.0-ec"
RETEST_LOOKBACK = 16


def _retest(
    bars: list[CandleBar],
    index: int,
    *,
    direction: str,
) -> FeatureValue:
    name = f"retest_{direction}"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, RETEST_VERSION, "index_out_of_range")
    if not bars[index].is_final:
        return FeatureValue.unknown(name, RETEST_VERSION, "bar_not_final")

    bos_side = "bullish" if direction == "long" else "bearish"
    start = max(0, index - RETEST_LOOKBACK)
    bos_index: int | None = None
    broken: Decimal | None = None
    for j in range(index - 1, start - 1, -1):
        bos = _bos(bars, j, direction=bos_side)
        if bos.status != TriState.TRUE or bos.value is not True:
            continue
        vol = compute_significant_volume(bars, j)
        if vol.status != TriState.TRUE or vol.value is not True:
            continue
        raw_broken = bos.meta.get("swing_price")
        if raw_broken is None:
            continue
        bos_index = j
        broken = Decimal(str(raw_broken))
        break
    if bos_index is None or broken is None:
        return FeatureValue.of(
            name,
            RETEST_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="no_prior_bos_with_volume",
            definition_id="ENT-001",
            lock_status="engineering_candidate",
        )

    bar = bars[index]
    overlaps = bar.low <= broken <= bar.high
    if not overlaps:
        return FeatureValue.of(
            name,
            RETEST_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="price_not_in_broken_level",
            bos_index=bos_index,
            broken_level=broken,
            definition_id="ENT-001",
            lock_status="engineering_candidate",
        )

    if direction == "long":
        swing_inv = last_swing(bars, as_of_index=index, kind="low")
        structure_holds = swing_inv is None or bar.close > swing_inv.price
    else:
        swing_inv = last_swing(bars, as_of_index=index, kind="high")
        structure_holds = swing_inv is None or bar.close < swing_inv.price
    if not structure_holds:
        return FeatureValue.of(
            name,
            RETEST_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="retest_invalidated",
            bos_index=bos_index,
            definition_id="ENT-001",
            lock_status="engineering_candidate",
        )

    low_vol = compute_low_volume(bars, index)
    if low_vol.status != TriState.TRUE or low_vol.value is not True:
        return FeatureValue.of(
            name,
            RETEST_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="retest_not_low_volume",
            bos_index=bos_index,
            broken_level=broken,
            definition_id="ENT-001",
            lock_status="engineering_candidate",
        )

    return FeatureValue.of(
        name,
        RETEST_VERSION,
        status=TriState.TRUE,
        value=True,
        bos_index=bos_index,
        broken_level=broken,
        definition_id="ENT-001",
        lock_status="engineering_candidate",
    )


def compute_retest_long(bars: list[CandleBar], index: int) -> FeatureValue:
    return _retest(bars, index, direction="long")


def compute_retest_short(bars: list[CandleBar], index: int) -> FeatureValue:
    return _retest(bars, index, direction="short")


register(
    FeatureSpec(
        name="retest_long",
        version=RETEST_VERSION,
        lookback=RETEST_LOOKBACK + 5,
        description="Low-volume retest of broken swing after bullish BOS (ENT-001)",
        lock_status="engineering_candidate",
        definition_id="ENT-001",
        dependencies=("bos_bullish", "low_volume", "significant_volume"),
        compute=compute_retest_long,
    )
)
register(
    FeatureSpec(
        name="retest_short",
        version=RETEST_VERSION,
        lookback=RETEST_LOOKBACK + 5,
        description="Low-volume retest of broken swing after bearish BOS (ENT-001)",
        lock_status="engineering_candidate",
        definition_id="ENT-001",
        dependencies=("bos_bearish", "low_volume", "significant_volume"),
        compute=compute_retest_short,
    )
)
