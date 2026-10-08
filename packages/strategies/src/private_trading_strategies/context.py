"""Shared playbook context for live decisions and replay. No look-ahead."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState
from private_trading_strategies.types import Direction

DEFAULT_ENTRY_PATH = "aggressive"


def build_playbook_context(
    bars: list[CandleBar],
    index: int,
    *,
    direction: Direction,
    min_rr: Decimal,
    entry_path: str = DEFAULT_ENTRY_PATH,
) -> dict[str, Any]:
    """Longs with EMA50 HTF. Enter on BOS+volume by default; retest only if safer."""
    close = bars[index].close
    swing_low = compute_feature("last_swing_low", bars, index)
    swing_high = compute_feature("last_swing_high", bars, index)
    atr = compute_feature("atr", bars, index)
    htf = compute_feature("ema_htf_bias", bars, index)
    retest_complete = False
    if entry_path == "safer":
        retest_name = "retest_long" if direction == Direction.LONG else "retest_short"
        retest = compute_feature(retest_name, bars, index)
        retest_complete = retest.status == TriState.TRUE and retest.value is True

    if direction == Direction.LONG:
        stop = swing_low.value if swing_low.status == TriState.TRUE else None
        if stop is None and atr.status == TriState.TRUE and atr.value:
            stop = close - Decimal(str(atr.value))
        structural_ok = stop is not None and stop < close
        risk = (close - stop) if stop is not None else None
    else:
        stop = swing_high.value if swing_high.status == TriState.TRUE else None
        if stop is None and atr.status == TriState.TRUE and atr.value:
            stop = close + Decimal(str(atr.value))
        structural_ok = stop is not None and stop > close
        risk = (stop - close) if stop is not None else None

    rr = None
    if risk is not None and risk > 0:
        rr = float(min_rr)

    htf_bias = htf.value if htf.status == TriState.TRUE else None

    return {
        "htf_bias": htf_bias,
        "structural_stop_ok": bool(structural_ok),
        "rr_to_tp1": rr,
        "entry_path": entry_path,
        "retest_complete": retest_complete,
        "_stop_price": str(stop) if stop is not None else None,
        "_entry_ref": str(close),
    }
