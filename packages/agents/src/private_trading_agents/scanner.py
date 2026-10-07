from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState

from private_trading_agents.workflow import DecisionAction, DecisionSnapshot, run_decision_workflow

SCANNER_VERSION = "0.1.0"
MIN_BARS = 25


@dataclass(slots=True)
class ScanOutcome:
    status: str
    fresh: bool
    actionable: bool
    action: str | None = None
    setup_state: str | None = None
    snapshot: DecisionSnapshot | None = None
    dedupe_key: str | None = None
    setup_anchor: str | None = None
    signal_type: str | None = None
    publishable: bool = False
    notes: list[str] = field(default_factory=list)


def dedupe_key(
    *,
    strategy_code: str,
    strategy_version_no: int,
    symbol: str,
    timeframe: str,
    setup_anchor: str,
    signal_type: str,
) -> str:
    return (
        f"{strategy_code}:v{strategy_version_no}:{symbol}:{timeframe}:"
        f"{setup_anchor}:{signal_type}"
    )


def setup_anchor(snapshot: DecisionSnapshot) -> str:
    """Anchor on the broken structure level so later candles of the same BOS do not re-alert."""
    features = snapshot.evidence.get("features") or {}
    key = "last_swing_high" if snapshot.direction == "long" else "last_swing_low"
    payload = features.get(key) or {}
    value = payload.get("value")
    if payload.get("status") == "true" and value is not None:
        return f"{key}@{Decimal(str(value)).normalize():f}"
    return f"bar@{snapshot.bar_open_time.isoformat()}"


def prefilter_passes(bars: list[CandleBar], index: int, *, direction: str = "long") -> bool:
    """Cheap deterministic prefilter so the full pipeline only runs on BOS candles."""
    name = "bos_bullish" if direction == "long" else "bos_bearish"
    return compute_feature(name, bars, index).status == TriState.TRUE


def evaluate_closed_candle(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    fresh: bool,
    actionable: bool,
    direction: str = "long",
) -> ScanOutcome:
    """Normalize → freshness → prefilter → strategy/risk/decision. Stale data never publishes."""
    if not fresh or not actionable:
        return ScanOutcome(
            status="skipped_stale",
            fresh=fresh,
            actionable=actionable,
            notes=["stale_or_not_actionable"],
        )
    if len(bars) < MIN_BARS:
        return ScanOutcome(
            status="skipped_insufficient_bars",
            fresh=fresh,
            actionable=actionable,
            notes=[f"bars={len(bars)} min={MIN_BARS}"],
        )
    index = len(bars) - 1
    if not prefilter_passes(bars, index, direction=direction):
        return ScanOutcome(
            status="prefilter_no_setup",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.NO_SETUP.value,
            setup_state="no_setup",
            notes=["prefilter_bos_false"],
        )
    snapshot = run_decision_workflow(
        bars,
        symbol=symbol,
        timeframe=timeframe,
        bar_index=index,
        direction=direction,
        data_fresh=fresh,
        market_actionable=actionable,
    )
    outcome = ScanOutcome(
        status="completed",
        fresh=fresh,
        actionable=actionable,
        action=snapshot.action.value,
        setup_state=snapshot.setup_state,
        snapshot=snapshot,
    )
    if snapshot.action == DecisionAction.ENTER:
        anchor = setup_anchor(snapshot)
        signal_type = f"enter_{snapshot.direction}"
        outcome.setup_anchor = anchor
        outcome.signal_type = signal_type
        outcome.dedupe_key = dedupe_key(
            strategy_code=snapshot.strategy_code,
            strategy_version_no=snapshot.strategy_version_no,
            symbol=symbol,
            timeframe=timeframe,
            setup_anchor=anchor,
            signal_type=signal_type,
        )
        outcome.publishable = True
    return outcome


def candidate_payload(snapshot: DecisionSnapshot) -> dict[str, Any]:
    return {
        "action": snapshot.action.value,
        "direction": snapshot.direction,
        "setup_state": snapshot.setup_state,
        "confidence_band": snapshot.confidence_band,
        "entry_price": None if snapshot.entry_price is None else str(snapshot.entry_price),
        "stop_price": None if snapshot.stop_price is None else str(snapshot.stop_price),
        "target_price": None if snapshot.target_price is None else str(snapshot.target_price),
        "rr_ratio": None if snapshot.rr_ratio is None else str(snapshot.rr_ratio),
        "hard_blockers": list(snapshot.hard_blockers),
        "scanner_version": SCANNER_VERSION,
    }
