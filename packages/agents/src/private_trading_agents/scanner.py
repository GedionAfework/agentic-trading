from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState
from private_trading_risk.portfolio import OpenExposure
from private_trading_strategies.multi_market import (
    TradingObjective,
    classify_market_regime,
    resolve_market_model,
)
from private_trading_strategies.specialist_registry import resolve_specialist_model
from private_trading_strategies.specialists import (
    SpecialistAction,
    SpecialistContext,
    evaluate_specialist,
)

from private_trading_agents.workflow import (
    DecisionAction,
    DecisionSnapshot,
    run_decision_workflow,
    run_specialist_decision,
)

SCANNER_VERSION = "0.3.0"
MIN_BARS = 50


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
    paper_eligible: bool = False
    notes: list[str] = field(default_factory=list)


def should_auto_open_paper(outcome: ScanOutcome) -> bool:
    return (
        outcome.paper_eligible
        and not outcome.publishable
        and outcome.action == DecisionAction.ENTER.value
        and outcome.snapshot is not None
        and outcome.snapshot.risk_approved
        and outcome.dedupe_key is not None
    )


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
    """Full pipeline only on BOS candles (v1 enters the impulse + volume bar)."""
    if direction != "long":
        return False
    return compute_feature("bos_bullish", bars, index).status == TriState.TRUE


def evaluate_closed_candle(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    fresh: bool,
    actionable: bool,
    direction: str = "long",
    min_rr: str = "2.0",
    asset_class: str = "crypto",
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
        min_rr=min_rr,
        asset_class=asset_class,
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


def evaluate_multi_market_closed_candle(
    entry_bars: list[CandleBar],
    higher_timeframe_bars: list[CandleBar],
    *,
    symbol: str,
    asset_class: str,
    objective: TradingObjective,
    fresh: bool,
    actionable: bool,
) -> ScanOutcome:
    """Resolve only validated paper models; unsupported combinations WAIT."""
    if not fresh or not actionable:
        return ScanOutcome(
            status="skipped_stale",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.WAIT.value,
            notes=["stale_or_not_actionable"],
        )
    regime = classify_market_regime(entry_bars, higher_timeframe_bars)
    if regime is None:
        return ScanOutcome(
            status="regime_unknown",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.WAIT.value,
            notes=["insufficient_closed_bars_for_regime"],
        )
    spec = resolve_market_model(
        symbol=symbol,
        regime=regime,
        objective=objective,
    )
    if spec is None or spec.asset_class != asset_class:
        return ScanOutcome(
            status="no_validated_model",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.WAIT.value,
            notes=[
                f"symbol={symbol}",
                f"regime={regime.value}",
                f"objective={objective.value}",
            ],
        )
    outcome = evaluate_closed_candle(
        entry_bars,
        symbol=symbol,
        timeframe=spec.entry_timeframe,
        fresh=fresh,
        actionable=actionable,
        direction=spec.direction,
        min_rr=str(spec.target_r),
        asset_class=spec.asset_class,
    )
    outcome.notes.extend(
        [
            f"paper_model={spec.code}:v{spec.version_no}",
            f"regime={regime.value}",
            f"objective={objective.value}",
        ]
    )
    if outcome.snapshot is not None:
        outcome.snapshot.strategy_code = spec.code
        outcome.snapshot.strategy_version_no = spec.version_no
        outcome.snapshot.evidence["paper_model"] = {
            "code": spec.code,
            "version_no": spec.version_no,
            "objective": spec.objective.value,
            "regime": regime.value,
            "paper_only": spec.paper_only,
            "live_alerts_allowed": spec.live_alerts_allowed,
            "partial_profit_at_r": spec.partial_profit_at_r,
            "partial_profit_fraction": spec.partial_profit_fraction,
            "move_stop_to_breakeven_after_partial": (
                spec.move_stop_to_breakeven_after_partial
            ),
            "max_bars_in_trade": spec.max_bars_in_trade,
        }
    if outcome.action == DecisionAction.ENTER.value and outcome.snapshot is not None:
        anchor = setup_anchor(outcome.snapshot)
        outcome.dedupe_key = dedupe_key(
            strategy_code=spec.code,
            strategy_version_no=spec.version_no,
            symbol=symbol,
            timeframe=spec.entry_timeframe,
            setup_anchor=anchor,
            signal_type=f"enter_{spec.direction}",
        )
        outcome.paper_eligible = True
        outcome.publishable = False
    return outcome


def evaluate_specialist_closed_candle(
    entry_bars: list[CandleBar],
    higher_timeframe_bars: list[CandleBar],
    *,
    symbol: str,
    asset_class: str,
    objective: TradingObjective,
    fresh: bool,
    actionable: bool,
    benchmark_bars: list[CandleBar] | None = None,
    open_exposures: tuple[OpenExposure, ...] = (),
    daily_realized_pnl_pct: Decimal = Decimal("0"),
) -> ScanOutcome:
    """Prefer a validated specialist; otherwise fall back to paper incumbents."""
    if not fresh or not actionable:
        return ScanOutcome(
            status="skipped_stale",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.WAIT.value,
            notes=["stale_or_not_actionable"],
        )
    regime = classify_market_regime(entry_bars, higher_timeframe_bars)
    if regime is None:
        return ScanOutcome(
            status="regime_unknown",
            fresh=fresh,
            actionable=actionable,
            action=DecisionAction.WAIT.value,
            notes=["insufficient_closed_bars_for_regime"],
        )
    specialist = resolve_specialist_model(
        symbol=symbol,
        regime=regime,
        objective=objective,
    )
    if specialist is None:
        return evaluate_multi_market_closed_candle(
            entry_bars,
            higher_timeframe_bars,
            symbol=symbol,
            asset_class=asset_class,
            objective=objective,
            fresh=fresh,
            actionable=actionable,
        )
    signal = evaluate_specialist(
        specialist.config,
        SpecialistContext(
            entry_bars=entry_bars,
            higher_timeframe_bars=higher_timeframe_bars,
            regime=regime,
            benchmark_bars=benchmark_bars,
        ),
    )
    snapshot = run_specialist_decision(
        entry_bars,
        symbol=symbol,
        timeframe="1h",
        asset_class=asset_class,
        model=specialist,
        signal=signal,
        data_fresh=fresh,
        market_actionable=actionable,
        open_exposures=open_exposures,
        daily_realized_pnl_pct=daily_realized_pnl_pct,
    )
    outcome = ScanOutcome(
        status="completed" if signal.action == SpecialistAction.ENTER else "specialist_wait",
        fresh=fresh,
        actionable=actionable,
        action=snapshot.action.value,
        setup_state=snapshot.setup_state,
        snapshot=snapshot,
        notes=[
            f"specialist={specialist.config.code}",
            f"family={specialist.config.family.value}",
            f"regime={regime.value}",
            f"objective={objective.value}",
        ],
    )
    if snapshot.action == DecisionAction.ENTER:
        snapshot.evidence["paper_model"] = {
            "code": specialist.config.code,
            "version_no": 1,
            "objective": objective.value,
            "regime": regime.value,
            "paper_only": True,
            "live_alerts_allowed": False,
            "partial_profit_at_r": (
                None
                if specialist.config.partial_at_r is None
                else float(specialist.config.partial_at_r)
            ),
            "partial_profit_fraction": float(specialist.config.partial_fraction),
            "move_stop_to_breakeven_after_partial": specialist.config.partial_at_r
            is not None,
            "max_bars_in_trade": specialist.config.max_bars,
        }
        outcome.setup_anchor = setup_anchor(snapshot)
        outcome.signal_type = f"enter_{snapshot.direction}"
        outcome.dedupe_key = dedupe_key(
            strategy_code=specialist.config.code,
            strategy_version_no=1,
            symbol=symbol,
            timeframe="1h",
            setup_anchor=outcome.setup_anchor,
            signal_type=outcome.signal_type,
        )
        outcome.paper_eligible = True
        outcome.publishable = False
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
