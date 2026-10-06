from __future__ import annotations

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.swings import SWING_RADIUS, last_swing
from private_trading_features.types import CandleBar, FeatureValue, TriState

STRUCTURE_VERSION = "1.0.0-ec"


def _bos(
    bars: list[CandleBar],
    index: int,
    *,
    direction: str,
) -> FeatureValue:
    """STR-002 EC: close beyond last confirmed swing (no wait candle)."""
    name = f"bos_{direction}"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, STRUCTURE_VERSION, "index_out_of_range")
    if not bars[index].is_final:
        return FeatureValue.unknown(name, STRUCTURE_VERSION, "bar_not_final")

    if direction == "bullish":
        swing = last_swing(bars, as_of_index=index, kind="high")
        if swing is None:
            return FeatureValue.unknown(name, STRUCTURE_VERSION, "no_swing_high")
        # Swing must be strictly before current bar (break on a later candle)
        if swing.index >= index:
            return FeatureValue.unknown(name, STRUCTURE_VERSION, "swing_not_prior")
        broke = bars[index].close > swing.price
    else:
        swing = last_swing(bars, as_of_index=index, kind="low")
        if swing is None:
            return FeatureValue.unknown(name, STRUCTURE_VERSION, "no_swing_low")
        if swing.index >= index:
            return FeatureValue.unknown(name, STRUCTURE_VERSION, "swing_not_prior")
        broke = bars[index].close < swing.price

    return FeatureValue.of(
        name,
        STRUCTURE_VERSION,
        status=TriState.TRUE if broke else TriState.FALSE,
        value=broke,
        swing_price=swing.price,
        swing_index=swing.index,
        close=bars[index].close,
        confirmation="close",
        wait_bars=0,
        definition_id="STR-002",
        lock_status="engineering_candidate",
    )


def compute_bos_bullish(bars: list[CandleBar], index: int) -> FeatureValue:
    return _bos(bars, index, direction="bullish")


def compute_bos_bearish(bars: list[CandleBar], index: int) -> FeatureValue:
    return _bos(bars, index, direction="bearish")


def _msb(
    bars: list[CandleBar],
    index: int,
    *,
    direction: str,
) -> FeatureValue:
    """STR-003 EC: MSB as opposite-side BOS after a prior same-side BOS in lookback.

    Distinct from BOS by requiring evidence of a prior BOS in the opposite
    direction within the confirmable swing window (structure flip).
    """
    name = f"msb_{direction}"
    bos = _bos(bars, index, direction=direction)
    if bos.status == TriState.UNKNOWN:
        return FeatureValue.unknown(name, STRUCTURE_VERSION, bos.reason or "bos_unknown")
    if bos.status == TriState.FALSE:
        return FeatureValue.of(
            name,
            STRUCTURE_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="no_bos_on_bar",
            definition_id="STR-003",
            lock_status="engineering_candidate",
        )

    opposite = "bearish" if direction == "bullish" else "bullish"
    # Scan prior final bars for opposite BOS without looking past index
    prior_opposite = False
    start = max(0, index - 50)
    for i in range(start, index):
        prior = _bos(bars, i, direction=opposite)
        if prior.status == TriState.TRUE and prior.value is True:
            prior_opposite = True
            break
    if not prior_opposite:
        return FeatureValue.of(
            name,
            STRUCTURE_VERSION,
            status=TriState.FALSE,
            value=False,
            reason="no_prior_opposite_bos",
            definition_id="STR-003",
            lock_status="engineering_candidate",
        )
    return FeatureValue.of(
        name,
        STRUCTURE_VERSION,
        status=TriState.TRUE,
        value=True,
        prior_opposite_bos=True,
        bos=bos.meta,
        definition_id="STR-003",
        lock_status="engineering_candidate",
    )


def compute_msb_bullish(bars: list[CandleBar], index: int) -> FeatureValue:
    return _msb(bars, index, direction="bullish")


def compute_msb_bearish(bars: list[CandleBar], index: int) -> FeatureValue:
    return _msb(bars, index, direction="bearish")


_lookback = SWING_RADIUS * 2 + 2

register(
    FeatureSpec(
        name="bos_bullish",
        version=STRUCTURE_VERSION,
        lookback=_lookback,
        description="Close above last confirmed swing high (STR-002 EC)",
        lock_status="engineering_candidate",
        definition_id="STR-002",
        dependencies=("last_swing_high",),
        compute=compute_bos_bullish,
    )
)
register(
    FeatureSpec(
        name="bos_bearish",
        version=STRUCTURE_VERSION,
        lookback=_lookback,
        description="Close below last confirmed swing low (STR-002 EC)",
        lock_status="engineering_candidate",
        definition_id="STR-002",
        dependencies=("last_swing_low",),
        compute=compute_bos_bearish,
    )
)
register(
    FeatureSpec(
        name="msb_bullish",
        version=STRUCTURE_VERSION,
        lookback=50,
        description="Bullish BOS after prior bearish BOS (STR-003 EC)",
        lock_status="engineering_candidate",
        definition_id="STR-003",
        dependencies=("bos_bullish",),
        compute=compute_msb_bullish,
    )
)
register(
    FeatureSpec(
        name="msb_bearish",
        version=STRUCTURE_VERSION,
        lookback=50,
        description="Bearish BOS after prior bullish BOS (STR-003 EC)",
        lock_status="engineering_candidate",
        definition_id="STR-003",
        dependencies=("bos_bearish",),
        compute=compute_msb_bearish,
    )
)
