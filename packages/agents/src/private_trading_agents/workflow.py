from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from private_trading_decision.labels import FEATURE_NAMES
from private_trading_decision.predict import LoadedModel
from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState
from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import default_policy_config
from private_trading_risk.types import Direction as RiskDirection
from private_trading_risk.types import InstrumentRiskMeta, RiskInput
from private_trading_strategies.evaluate import evaluate_strategy
from private_trading_strategies.types import Direction, SetupState
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

from private_trading_agents.explain import grounded_explanation
from private_trading_agents.vision import VisionVerdict

WORKFLOW_VERSION = "0.1.0"


class DecisionAction(StrEnum):
    ENTER = "ENTER"
    WAIT = "WAIT"
    HOLD = "HOLD"
    EXIT = "EXIT"
    NO_SETUP = "NO_SETUP"


@dataclass(slots=True)
class CitationRef:
    citation_id: str
    excerpt: str
    document_id: str | None = None


@dataclass(slots=True)
class DecisionSnapshot:
    symbol: str
    timeframe: str
    bar_open_time: datetime
    action: DecisionAction
    direction: str
    setup_state: str
    confidence_band: str
    strategy_code: str
    strategy_version_no: int
    risk_approved: bool
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    rr_ratio: Decimal | None
    model_id: UUID | None
    model_score: float | None
    model_band: str | None
    explanation: str
    explanation_source: str
    evidence: dict[str, Any]
    workflow: list[dict[str, str]]
    hard_blockers: list[str] = field(default_factory=list)


def _feature_payload(bars: list[CandleBar], index: int) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in FEATURE_NAMES:
        value = compute_feature(name, bars, index)
        numeric = value.value
        if isinstance(numeric, Decimal):
            numeric = float(numeric)
        payload[name] = {"status": value.status.value, "value": numeric, "reason": value.reason}
    return payload


def _prices(
    bars: list[CandleBar], index: int, *, direction: Direction, min_rr: Decimal
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    close = bars[index].close
    atr = compute_feature("atr", bars, index)
    if direction == Direction.LONG:
        swing = compute_feature("last_swing_low", bars, index)
        stop = swing.value if swing.status == TriState.TRUE else None
        if stop is None and atr.status == TriState.TRUE and atr.value:
            stop = close - Decimal(str(atr.value))
        if stop is None or stop >= close:
            return close, None, None
        risk = close - Decimal(str(stop))
        return close, Decimal(str(stop)), close + risk * min_rr
    swing = compute_feature("last_swing_high", bars, index)
    stop = swing.value if swing.status == TriState.TRUE else None
    if stop is None and atr.status == TriState.TRUE and atr.value:
        stop = close + Decimal(str(atr.value))
    if stop is None or stop <= close:
        return close, None, None
    risk = Decimal(str(stop)) - close
    return close, Decimal(str(stop)), close - risk * min_rr


def _confidence(
    *,
    action: DecisionAction,
    risk_approved: bool,
    model_band: str | None,
    model_mode: str | None,
) -> str:
    if action in {DecisionAction.NO_SETUP, DecisionAction.EXIT}:
        return "none"
    if action == DecisionAction.WAIT or not risk_approved:
        return "low"
    if action == DecisionAction.HOLD:
        return "medium"
    if model_mode == "champion" and model_band == "high":
        return "high"
    return "medium"


def run_decision_workflow(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    bar_index: int | None = None,
    direction: str = "long",
    data_fresh: bool = True,
    market_actionable: bool = True,
    position_state: Literal["flat", "open"] = "flat",
    citations: list[CitationRef] | None = None,
    model: LoadedModel | None = None,
    model_id: UUID | None = None,
    model_mode: str | None = None,
    min_rr: str = "2.0",
    vision: VisionVerdict | None = None,
) -> DecisionSnapshot:
    """AG-01 orchestrates AG-04, AG-05, AG-06, optional AG-09, then AG-02 explanation."""
    index = len(bars) - 1 if bar_index is None else bar_index
    bar = bars[index]
    side = Direction(direction)
    workflow: list[dict[str, str]] = [
        {"agent": "AG-01", "status": "running", "note": "decision workflow"},
        {
            "agent": "AG-04",
            "status": "ok",
            "note": f"{symbol} {timeframe} bar {index} fresh={data_fresh}",
        },
        {
            "agent": "AG-03",
            "status": "skipped" if vision is None else vision.status,
            "note": "vision not attached" if vision is None else "supporting evidence only",
        },
        {"agent": "AG-08", "status": "skipped", "note": "journal is a later phase"},
    ]
    features = _feature_payload(bars, index)
    min_rr_dec = Decimal(min_rr)
    entry, stop, target = _prices(bars, index, direction=side, min_rr=min_rr_dec)
    structural_ok = stop is not None and target is not None
    strategy = build_wyckoff_hdm_v1(
        version_no=1, advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    assessment = evaluate_strategy(
        strategy,
        direction=side,
        features=features,
        context={
            "htf_bias": side.value,
            "structural_stop_ok": structural_ok,
            "rr_to_tp1": float(min_rr_dec) if structural_ok else None,
            "entry_path": "aggressive",
            "retest_complete": False,
        },
    )
    workflow.append(
        {
            "agent": "AG-05",
            "status": "ok",
            "note": f"setup_state={assessment.setup_state.value}",
        }
    )

    hard_blockers = list(assessment.blockers)
    if not data_fresh:
        hard_blockers.append("stale_market_data")
    if not market_actionable:
        hard_blockers.append("market_not_actionable")
    workflow.append(
        {
            "agent": "AG-07",
            "status": "ok" if not hard_blockers else "blocked",
            "note": "hard no-trade gates",
        }
    )

    risk = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=RiskInput(
            direction=RiskDirection(side.value),
            entry=entry,
            stop=stop,
            target_1=target,
            data_fresh=data_fresh,
            market_actionable=market_actionable,
            account_equity=Decimal("10000"),
            instrument=InstrumentRiskMeta(
                asset_class="crypto",
                price_tick=Decimal("0.01"),
                qty_step=Decimal("0.001"),
                min_notional=Decimal("10"),
            ),
        ),
    )
    for blocker in risk.hard_blockers:
        if blocker not in hard_blockers:
            hard_blockers.append(blocker)
    workflow.append(
        {
            "agent": "AG-06",
            "status": "approved" if risk.approved else "veto",
            "note": "risk veto",
        }
    )

    gates_open = (
        data_fresh
        and market_actionable
        and assessment.setup_state == SetupState.READY_FOR_REVIEW
        and risk.approved
    )
    model_score: float | None = None
    model_band: str | None = None
    model_says_enter = False
    if model is not None and gates_open:
        ranked = model.decide(
            features,
            strategy_ready=True,
            risk_approved=True,
            mode=model_mode or "shadow",
        )
        model_score = ranked.score
        model_band = ranked.band
        model_says_enter = ranked.recommendation == "ENTER"
        workflow.append(
            {
                "agent": "AG-09",
                "status": "scored",
                "note": f"band={model_band} mode={model_mode or 'shadow'}",
            }
        )
    else:
        workflow.append(
            {
                "agent": "AG-09",
                "status": "skipped",
                "note": "ranker omitted or gates already closed",
            }
        )

    if position_state == "open":
        action = DecisionAction.HOLD if gates_open else DecisionAction.EXIT
    elif assessment.setup_state == SetupState.NO_SETUP and data_fresh and market_actionable:
        action = DecisionAction.NO_SETUP
    elif not gates_open:
        action = DecisionAction.WAIT
    elif model is not None and (model_mode or "shadow") == "champion" and not model_says_enter:
        action = DecisionAction.WAIT
        hard_blockers.append("model_abstain")
    else:
        action = DecisionAction.ENTER

    if vision is not None and vision.needs_clarification and action == DecisionAction.ENTER:
        action = DecisionAction.WAIT
        if vision.blocker and vision.blocker not in hard_blockers:
            hard_blockers.append(vision.blocker)

    band = _confidence(
        action=action,
        risk_approved=risk.approved,
        model_band=model_band,
        model_mode=model_mode,
    )
    citation_rows = [
        {"citation_id": item.citation_id, "document_id": item.document_id, "excerpt": item.excerpt}
        for item in (citations or [])
    ]
    facts: dict[str, Any] = {
        "action": action.value,
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_open_time": bar.open_time.isoformat(),
        "strategy_code": assessment.strategy_code,
        "strategy_version_no": assessment.strategy_version_no,
        "setup_state": assessment.setup_state.value,
        "hard_blockers": hard_blockers,
        "risk_approved": risk.approved,
        "entry_price": entry if risk.entry_reference is None else risk.entry_reference,
        "stop_price": risk.stop_price if risk.stop_price is not None else stop,
        "target_price": risk.target_1 if risk.target_1 is not None else target,
        "rr_ratio": risk.rr_ratio,
        "features": features,
        "citations": citation_rows,
        "model_score": model_score,
        "model_band": model_band,
        "model_invoked": model is not None,
        "confidence_band": band,
        "extra_numbers": [min_rr],
    }
    # Prefer the risk engine's own figures when it computed them.
    if risk.entry_reference is not None:
        facts["entry_price"] = risk.entry_reference
    explanation = grounded_explanation(facts)
    workflow.append({"agent": "AG-02", "status": "ok", "note": "grounded explanation"})
    workflow[0] = {"agent": "AG-01", "status": "ok", "note": f"action={action.value}"}

    return DecisionSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        bar_open_time=bar.open_time,
        action=action,
        direction=side.value,
        setup_state=assessment.setup_state.value,
        confidence_band=band,
        strategy_code=assessment.strategy_code,
        strategy_version_no=assessment.strategy_version_no,
        risk_approved=risk.approved,
        entry_price=facts["entry_price"],
        stop_price=facts["stop_price"],
        target_price=facts["target_price"],
        rr_ratio=facts["rr_ratio"],
        model_id=model_id,
        model_score=model_score,
        model_band=model_band,
        explanation=explanation,
        explanation_source="deterministic",
        evidence={
            "features": features,
            "strategy_blockers": list(assessment.blockers),
            "risk_blockers": list(risk.hard_blockers),
            "citations": citation_rows,
            "position_state": position_state,
            "workflow_version": WORKFLOW_VERSION,
        },
        workflow=workflow,
        hard_blockers=hard_blockers,
    )
