from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.types import CandleBar, FeatureValue, TriState

SWING_VERSION = "1.0.0-ec"
# STR-001 EC: N bars left and right must be strictly lower/higher.
SWING_RADIUS = 2


@dataclass(slots=True, frozen=True)
class SwingPoint:
    index: int
    open_time: datetime
    price: Decimal
    kind: str  # high | low


def confirmed_swings(
    bars: list[CandleBar],
    *,
    as_of_index: int,
    radius: int = SWING_RADIUS,
) -> list[SwingPoint]:
    """Return swings confirmed without look-ahead.

    A candidate at j is confirmed only when as_of_index >= j + radius
    and left/right windows are fully available within [0, as_of_index].
    """
    if as_of_index < 0 or as_of_index >= len(bars):
        return []
    swings: list[SwingPoint] = []
    # Latest confirmable pivot index
    last_pivot = as_of_index - radius
    for j in range(radius, last_pivot + 1):
        window = bars[j - radius : j + radius + 1]
        mid = bars[j]
        highs = [b.high for b in window]
        lows = [b.low for b in window]
        if mid.high == max(highs) and highs.count(mid.high) == 1:
            swings.append(SwingPoint(j, mid.open_time, mid.high, "high"))
        if mid.low == min(lows) and lows.count(mid.low) == 1:
            swings.append(SwingPoint(j, mid.open_time, mid.low, "low"))
    return swings


def last_swing(
    bars: list[CandleBar],
    *,
    as_of_index: int,
    kind: str,
    radius: int = SWING_RADIUS,
) -> SwingPoint | None:
    swings = [s for s in confirmed_swings(bars, as_of_index=as_of_index, radius=radius) if s.kind == kind]
    return swings[-1] if swings else None


def compute_last_swing_high(bars: list[CandleBar], index: int) -> FeatureValue:
    name = "last_swing_high"
    swing = last_swing(bars, as_of_index=index, kind="high")
    if swing is None:
        return FeatureValue.unknown(
            name, SWING_VERSION, "no_confirmed_swing", radius=SWING_RADIUS
        )
    return FeatureValue.of(
        name,
        SWING_VERSION,
        status=TriState.TRUE,
        value=swing.price,
        bar_index=swing.index,
        open_time=swing.open_time.isoformat(),
        definition_id="STR-001",
        lock_status="engineering_candidate",
    )


def compute_last_swing_low(bars: list[CandleBar], index: int) -> FeatureValue:
    name = "last_swing_low"
    swing = last_swing(bars, as_of_index=index, kind="low")
    if swing is None:
        return FeatureValue.unknown(
            name, SWING_VERSION, "no_confirmed_swing", radius=SWING_RADIUS
        )
    return FeatureValue.of(
        name,
        SWING_VERSION,
        status=TriState.TRUE,
        value=swing.price,
        bar_index=swing.index,
        open_time=swing.open_time.isoformat(),
        definition_id="STR-001",
        lock_status="engineering_candidate",
    )


register(
    FeatureSpec(
        name="last_swing_high",
        version=SWING_VERSION,
        lookback=SWING_RADIUS * 2 + 1,
        description=f"Last confirmed swing high (radius={SWING_RADIUS})",
        lock_status="engineering_candidate",
        definition_id="STR-001",
        compute=compute_last_swing_high,
    )
)
register(
    FeatureSpec(
        name="last_swing_low",
        version=SWING_VERSION,
        lookback=SWING_RADIUS * 2 + 1,
        description=f"Last confirmed swing low (radius={SWING_RADIUS})",
        lock_status="engineering_candidate",
        definition_id="STR-001",
        compute=compute_last_swing_low,
    )
)
