from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from private_trading_decision.predict import LoadedModel
from private_trading_features.types import CandleBar
from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import default_policy_config
from private_trading_risk.portfolio import (
    OpenExposure,
    PortfolioRiskInput,
    assess_portfolio_risk,
    specialist_risk_pct,
)
from private_trading_risk.types import Direction as RiskDirection
from private_trading_risk.types import InstrumentRiskMeta, RiskInput
from private_trading_strategies.specialist_registry import ValidatedSpecialistModel
from private_trading_strategies.specialists import SpecialistAction, SpecialistSignal
from private_trading_strategies.types import Direction, SetupState

from private_trading_agents.adapters import candles_to_models, feature_models_to_payload
from private_trading_agents.agent_runtime import agent_session
from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    CitationModel,
    DecisionActionName,
    JournalAgentIn,
    KnowledgeAgentIn,
    MarketDataAgentIn,
    OrchestratorAgentIn,
    RiskAgentIn,
    SignalAgentIn,
    StrategyAgentIn,
    VisionAgentIn,
)
from private_trading_agents.explain import grounded_explanation
from private_trading_agents.roles import (
    run_decision_ml_agent,
    run_journal_agent,
    run_knowledge_agent,
    run_market_data_agent,
    run_risk_agent,
    run_signal_agent,
    run_strategy_agent,
    run_vision_agent,
)
from private_trading_agents.vision import VisionVerdict

WORKFLOW_VERSION = "0.2.0"


class DecisionAction(StrEnum):
    ENTER = "ENTER"
    WAIT = "WAIT"
    HOLD = "HOLD"
    EXIT = "EXIT"
    NO_SETUP = "NO_SETUP"


# Pydantic citation contract; keep name for callers/tests.
CitationRef = CitationModel


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
    tool_traces: list[dict[str, Any]] = field(default_factory=list)


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
    asset_class: str = "crypto",
    vision: VisionVerdict | None = None,
    mode: Literal["deterministic", "agentic"] = "deterministic",
) -> DecisionSnapshot:
    """AG-01 orchestrates AG-02..AG-09.

    mode=deterministic (default): fixed specialist sequence (paper/scanner safe).
    mode=agentic: AG-01 routing-tool loop under the policy graph.
    """
    from private_trading_agents.contracts import AgentId
    from private_trading_agents.orchestrator import ag01_budget, run_agentic_orchestrator

    budgets = {AgentId.AG01_ORCHESTRATOR: ag01_budget()} if mode == "agentic" else {}
    with agent_session(budgets=budgets) as session:
        if mode == "agentic":
            snapshot = run_agentic_orchestrator(
                bars,
                symbol=symbol,
                timeframe=timeframe,
                bar_index=bar_index,
                direction=direction,
                data_fresh=data_fresh,
                market_actionable=market_actionable,
                position_state=position_state,
                citations=citations,
                model=model,
                model_id=model_id,
                model_mode=model_mode,
                min_rr=min_rr,
                asset_class=asset_class,
                vision=vision,
            )
        else:
            snapshot = _run_decision_workflow(
                bars,
                symbol=symbol,
                timeframe=timeframe,
                bar_index=bar_index,
                direction=direction,
                data_fresh=data_fresh,
                market_actionable=market_actionable,
                position_state=position_state,
                citations=citations,
                model=model,
                model_id=model_id,
                model_mode=model_mode,
                min_rr=min_rr,
                asset_class=asset_class,
                vision=vision,
            )
        traces = session.as_dicts()
        evidence = dict(snapshot.evidence)
        evidence["tool_traces"] = traces
        evidence["agent_runtime"] = "v1"
        evidence["orchestrator_mode"] = mode
        evidence["workflow_version"] = WORKFLOW_VERSION
        return replace(snapshot, tool_traces=traces, evidence=evidence)


def _run_decision_workflow(
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
    asset_class: str = "crypto",
    vision: VisionVerdict | None = None,
) -> DecisionSnapshot:
    citation_models = [
        CitationModel.model_validate(
            item.model_dump() if hasattr(item, "model_dump") else item
        )
        for item in (citations or [])
    ]
    vision_in = None
    if vision is not None:
        vision_in = VisionAgentIn(
            attached=True,
            status=vision.status,
            consistent=vision.consistent,
            needs_clarification=vision.needs_clarification,
            blocker=vision.blocker,
        )
    OrchestratorAgentIn.model_validate(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": candles_to_models(bars),
            "bar_index": bar_index,
            "direction": direction,
            "data_fresh": data_fresh,
            "market_actionable": market_actionable,
            "position_state": position_state,
            "citations": citation_models,
            "min_rr": min_rr,
            "asset_class": asset_class,
            "model_id": model_id,
            "model_mode": model_mode,
            "model_present": model is not None,
            "vision": vision_in,
        }
    )

    workflow: list[dict[str, str]] = [
        AgentStep(
            agent=AgentId.AG01_ORCHESTRATOR,
            status="running",
            note="decision workflow",
        ).as_workflow_dict()
    ]

    market = run_market_data_agent(
        MarketDataAgentIn(
            symbol=symbol,
            timeframe=timeframe,
            bars=candles_to_models(bars),
            data_fresh=data_fresh,
            market_actionable=market_actionable,
            bar_index=bar_index,
        )
    )
    workflow.append(market.step.as_workflow_dict())

    vision_out = run_vision_agent(vision_in)
    workflow.append(vision_out.step.as_workflow_dict())

    journal_out = run_journal_agent(JournalAgentIn())
    workflow.append(journal_out.step.as_workflow_dict())

    strategy = run_strategy_agent(
        StrategyAgentIn(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,  # type: ignore[arg-type]
            features=market.features,
            bars=candles_to_models(bars),
            bar_index=market.bar_index,
            min_rr=Decimal(min_rr),
            asset_class=asset_class,
        )
    )
    workflow.append(strategy.step.as_workflow_dict())

    signal = run_signal_agent(
        SignalAgentIn(
            setup_state=strategy.setup_state,
            data_fresh=market.data_fresh,
            market_actionable=market.market_actionable,
            hard_blockers=list(strategy.blockers),
        )
    )
    workflow.append(signal.step.as_workflow_dict())
    hard_blockers = list(signal.hard_blockers)

    risk = run_risk_agent(
        RiskAgentIn(
            direction=direction,  # type: ignore[arg-type]
            entry=strategy.entry_price,
            stop=strategy.stop_price,
            target=strategy.target_price,
            data_fresh=market.data_fresh,
            market_actionable=market.market_actionable,
            asset_class=asset_class,
            prior_blockers=hard_blockers,
        )
    )
    workflow.append(risk.step.as_workflow_dict())
    hard_blockers = list(risk.hard_blockers)

    gates_open = signal.gates_open_candidate and risk.approved
    ml = run_decision_ml_agent(
        {
            "features": market.features,
            "gates_open": gates_open,
            "model_mode": model_mode,
            "model_present": model is not None,
        },
        model=model,
    )
    workflow.append(ml.step.as_workflow_dict())
    model_score = ml.model_score
    model_band = ml.model_band
    model_says_enter = ml.recommends_enter

    if position_state == "open":
        action = DecisionAction.HOLD if gates_open else DecisionAction.EXIT
    elif (
        strategy.setup_state == SetupState.NO_SETUP.value
        and market.data_fresh
        and market.market_actionable
    ):
        action = DecisionAction.NO_SETUP
    elif not gates_open:
        action = DecisionAction.WAIT
    elif model is not None and (model_mode or "shadow") == "champion" and not model_says_enter:
        action = DecisionAction.WAIT
        hard_blockers.append("model_abstain")
    else:
        action = DecisionAction.ENTER

    if vision_out.needs_clarification and action == DecisionAction.ENTER:
        action = DecisionAction.WAIT
        if vision_out.blocker and vision_out.blocker not in hard_blockers:
            hard_blockers.append(vision_out.blocker)

    band = _confidence(
        action=action,
        risk_approved=risk.approved,
        model_band=model_band,
        model_mode=model_mode,
    )
    features = feature_models_to_payload(market.features)
    citation_rows = [item.model_dump() for item in citation_models]
    facts: dict[str, Any] = {
        "action": action.value,
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_open_time": market.bar_open_time.isoformat(),
        "strategy_code": strategy.strategy_code,
        "strategy_version_no": strategy.strategy_version_no,
        "setup_state": strategy.setup_state,
        "hard_blockers": hard_blockers,
        "risk_approved": risk.approved,
        "entry_price": risk.entry_price,
        "stop_price": risk.stop_price,
        "target_price": risk.target_price,
        "rr_ratio": risk.rr_ratio,
        "features": features,
        "citations": citation_rows,
        "model_score": model_score,
        "model_band": model_band,
        "model_invoked": model is not None,
        "confidence_band": band,
        "extra_numbers": [min_rr],
    }
    knowledge = run_knowledge_agent(KnowledgeAgentIn(facts=facts, citations=citation_models))
    workflow.append(knowledge.step.as_workflow_dict())
    workflow[0] = AgentStep(
        agent=AgentId.AG01_ORCHESTRATOR,
        status="ok",
        note=f"action={action.value}",
    ).as_workflow_dict()

    # Validate final orchestrator envelope (action name must be a known enum).
    DecisionActionName(action.value)

    return DecisionSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        bar_open_time=market.bar_open_time,
        action=action,
        direction=strategy.direction,
        setup_state=strategy.setup_state,
        confidence_band=band,
        strategy_code=strategy.strategy_code,
        strategy_version_no=strategy.strategy_version_no,
        risk_approved=risk.approved,
        entry_price=facts["entry_price"],
        stop_price=facts["stop_price"],
        target_price=facts["target_price"],
        rr_ratio=facts["rr_ratio"],
        model_id=model_id,
        model_score=model_score,
        model_band=model_band,
        explanation=knowledge.explanation,
        explanation_source=knowledge.explanation_source,
        evidence={
            "features": features,
            "strategy_blockers": list(strategy.blockers),
            "risk_blockers": list(risk.hard_blockers),
            "citations": citation_rows,
            "position_state": position_state,
            "workflow_version": WORKFLOW_VERSION,
            "contracts": "pydantic_v1",
        },
        workflow=workflow,
        hard_blockers=hard_blockers,
    )


def run_specialist_decision(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    asset_class: str,
    model: ValidatedSpecialistModel,
    signal: SpecialistSignal,
    data_fresh: bool = True,
    market_actionable: bool = True,
    open_exposures: tuple[OpenExposure, ...] = (),
    daily_realized_pnl_pct: Decimal = Decimal("0"),
) -> DecisionSnapshot:
    """Paper-only specialist path: plugin signal, trade risk, then portfolio veto."""
    index = len(bars) - 1
    bar = bars[index]
    workflow: list[dict[str, str]] = [
        {"agent": "AG-01", "status": "ok", "note": "specialist workflow"},
        {"agent": "AG-04", "status": "ok", "note": f"{symbol} {timeframe}"},
        {
            "agent": "AG-05",
            "status": "ok" if signal.action == SpecialistAction.ENTER else "wait",
            "note": signal.reason or signal.family.value,
        },
    ]
    hard_blockers: list[str] = []
    if not data_fresh:
        hard_blockers.append("stale_market_data")
    if not market_actionable:
        hard_blockers.append("market_not_actionable")
    if signal.action != SpecialistAction.ENTER:
        hard_blockers.append(signal.reason or "specialist_wait")

    entry = signal.entry_reference
    stop = signal.stop_price
    target = signal.target_price
    side = Direction(signal.direction or "long")

    proposed_risk = specialist_risk_pct(
        objective=model.objective.value,
        mean_r=model.validation.mean_r,
        max_drawdown_r=model.validation.max_drawdown_r,
    )
    risk = assess_risk(
        policy_code=f"specialist-{asset_class}",
        policy_version_no=1,
        policy_config=default_policy_config(
            asset_class=asset_class,
            min_rr=float(model.config.rr),
            max_risk_pct=float(proposed_risk) if proposed_risk > 0 else 0.1,
        ),
        risk_input=RiskInput(
            direction=RiskDirection(side.value),
            entry=entry,
            stop=stop,
            target_1=target,
            data_fresh=data_fresh,
            market_actionable=market_actionable,
            account_equity=Decimal("10000"),
            open_risk_pct=sum(
                (item.risk_pct for item in open_exposures),
                Decimal("0"),
            )
            + proposed_risk,
            instrument=InstrumentRiskMeta(
                asset_class=asset_class,
                price_tick=(
                    Decimal("0.00001") if asset_class == "forex" else Decimal("0.01")
                ),
                qty_step=Decimal("0.01") if asset_class == "forex" else Decimal("0.001"),
                min_notional=Decimal("0") if asset_class == "forex" else Decimal("10"),
            ),
        ),
    )
    for blocker in risk.hard_blockers:
        if blocker not in hard_blockers:
            hard_blockers.append(blocker)
    portfolio = assess_portfolio_risk(
        PortfolioRiskInput(
            proposed_symbol=symbol,
            proposed_asset_class=asset_class,
            proposed_direction=side.value,
            proposed_risk_pct=proposed_risk,
            open_exposures=open_exposures,
            daily_realized_pnl_pct=daily_realized_pnl_pct,
        )
    )
    for blocker in portfolio.blockers:
        if blocker not in hard_blockers:
            hard_blockers.append(blocker)
    workflow.extend(
        [
            {
                "agent": "AG-06",
                "status": "approved" if risk.approved and portfolio.approved else "veto",
                "note": "trade and portfolio risk",
            },
            {"agent": "AG-09", "status": "skipped", "note": "specialist registry, no ML override"},
        ]
    )
    approved = (
        data_fresh
        and market_actionable
        and signal.action == SpecialistAction.ENTER
        and risk.approved
        and portfolio.approved
        and proposed_risk > 0
        and model.paper_only
        and not model.live_alerts_allowed
    )
    action = DecisionAction.ENTER if approved else DecisionAction.WAIT
    if not model.paper_only or model.live_alerts_allowed:
        action = DecisionAction.WAIT
        hard_blockers.append("specialist_not_paper_only")
    facts: dict[str, Any] = {
        "action": action.value,
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_open_time": bar.open_time.isoformat(),
        "strategy_code": model.config.code,
        "strategy_version_no": 1,
        "setup_state": "ready_for_review" if approved else "wait",
        "hard_blockers": hard_blockers,
        "risk_approved": approved,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "rr_ratio": risk.rr_ratio,
        "features": {},
        "citations": [],
        "model_score": None,
        "model_band": None,
        "model_invoked": False,
        "confidence_band": "medium" if approved else "low",
        "extra_numbers": [str(model.config.rr)],
    }
    explanation = grounded_explanation(facts)
    workflow.append({"agent": "AG-02", "status": "ok", "note": "grounded explanation"})
    return DecisionSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        bar_open_time=bar.open_time,
        action=action,
        direction=side.value,
        setup_state=str(facts["setup_state"]),
        confidence_band=str(facts["confidence_band"]),
        strategy_code=model.config.code,
        strategy_version_no=1,
        risk_approved=approved,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        rr_ratio=risk.rr_ratio,
        model_id=None,
        model_score=None,
        model_band=None,
        explanation=explanation,
        explanation_source="deterministic",
        evidence={
            "specialist": {
                "family": signal.family.value,
                "reason": signal.reason,
                "paper_only": model.paper_only,
                "live_alerts_allowed": False,
                "partial_profit_at_r": (
                    None
                    if model.config.partial_at_r is None
                    else float(model.config.partial_at_r)
                ),
                "partial_profit_fraction": float(model.config.partial_fraction),
                "max_bars_in_trade": model.config.max_bars,
            },
            "portfolio_blockers": list(portfolio.blockers),
            "risk_blockers": list(risk.hard_blockers),
            "workflow_version": WORKFLOW_VERSION,
        },
        workflow=workflow,
        hard_blockers=hard_blockers,
    )
