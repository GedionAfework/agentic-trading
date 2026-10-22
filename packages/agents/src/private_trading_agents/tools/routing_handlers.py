"""AG-01 routing tool handlers — call specialist roles only."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_agents.contracts import (
    JournalAgentIn,
    KnowledgeAgentIn,
    MarketDataAgentIn,
    RiskAgentIn,
    SignalAgentIn,
    StrategyAgentIn,
)
from private_trading_agents.orchestrator_state import OrchestratorState
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.policy import PolicyViolationError
from private_trading_agents.tools.routing_schemas import (
    RoutingEmptyIn,
    RoutingStepOut,
    WorkflowFinishOut,
)


def _roles():
    # Lazy import avoids catalog → routing → roles → runtime → catalog cycles.
    from private_trading_agents import roles as roles_mod

    return roles_mod


def _state(context: ToolContext | None) -> OrchestratorState:
    if context is None or "orchestrator_state" not in context.extras:
        raise PolicyViolationError(
            "Routing tools require orchestrator_state in ToolContext",
            details={"policy": "routing_context_required"},
        )
    state = context.extras["orchestrator_state"]
    if not isinstance(state, OrchestratorState):
        raise PolicyViolationError(
            "Invalid orchestrator_state type",
            details={"policy": "routing_context_required"},
        )
    return state


def _begin(state: OrchestratorState, tool: ToolId) -> None:
    state.ensure_workflow_head()
    state.policy.assert_can_invoke(tool)


def _end(state: OrchestratorState, tool: ToolId, status: str, note: str) -> RoutingStepOut:
    state.policy.mark_completed(tool)
    return RoutingStepOut(tool=tool.value, status=status, note=note)


def handle_agent_run_market_data(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_MARKET_DATA
    _begin(state, tool)
    market = _roles().run_market_data_agent(
        MarketDataAgentIn(
            symbol=state.symbol,
            timeframe=state.timeframe,
            bars=state.candle_models(),
            data_fresh=state.data_fresh,
            market_actionable=state.market_actionable,
            bar_index=state.bar_index,
        )
    )
    state.market = market
    state.workflow.append(market.step.as_workflow_dict())
    return _end(state, tool, market.step.status, market.step.note)


def handle_agent_run_vision(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_VISION
    _begin(state, tool)
    vision_out = _roles().run_vision_agent(state.vision_in)
    state.vision_out = vision_out
    state.workflow.append(vision_out.step.as_workflow_dict())
    return _end(state, tool, vision_out.step.status, vision_out.step.note)


def handle_agent_run_journal(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_JOURNAL
    _begin(state, tool)
    journal_out = _roles().run_journal_agent(JournalAgentIn())
    state.journal_out = journal_out
    state.workflow.append(journal_out.step.as_workflow_dict())
    return _end(state, tool, journal_out.step.status, journal_out.step.note)


def handle_agent_run_strategy(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_STRATEGY
    _begin(state, tool)
    if state.market is None:
        raise PolicyViolationError("market_data required before strategy")
    strategy = _roles().run_strategy_agent(
        StrategyAgentIn(
            symbol=state.symbol,
            timeframe=state.timeframe,
            direction=state.direction,  # type: ignore[arg-type]
            features=state.market.features,
            bars=state.candle_models(),
            bar_index=state.market.bar_index,
            min_rr=Decimal(state.min_rr),
            asset_class=state.asset_class,
        )
    )
    state.strategy = strategy
    state.workflow.append(strategy.step.as_workflow_dict())
    return _end(state, tool, strategy.step.status, strategy.step.note)


def handle_agent_run_signal(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_SIGNAL
    _begin(state, tool)
    if state.market is None or state.strategy is None:
        raise PolicyViolationError("strategy required before signal")
    signal = _roles().run_signal_agent(
        SignalAgentIn(
            setup_state=state.strategy.setup_state,
            data_fresh=state.market.data_fresh,
            market_actionable=state.market.market_actionable,
            hard_blockers=list(state.strategy.blockers),
        )
    )
    state.signal = signal
    state.hard_blockers = list(signal.hard_blockers)
    state.workflow.append(signal.step.as_workflow_dict())
    return _end(state, tool, signal.step.status, signal.step.note)


def handle_agent_run_risk(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_RISK
    _begin(state, tool)
    if state.market is None or state.strategy is None or state.signal is None:
        raise PolicyViolationError("signal required before risk")
    risk = _roles().run_risk_agent(
        RiskAgentIn(
            direction=state.direction,  # type: ignore[arg-type]
            entry=state.strategy.entry_price,
            stop=state.strategy.stop_price,
            target=state.strategy.target_price,
            data_fresh=state.market.data_fresh,
            market_actionable=state.market.market_actionable,
            asset_class=state.asset_class,
            prior_blockers=list(state.hard_blockers),
        )
    )
    state.risk = risk
    state.hard_blockers = list(risk.hard_blockers)
    state.workflow.append(risk.step.as_workflow_dict())
    return _end(state, tool, risk.step.status, risk.step.note)


def handle_agent_run_ml(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_ML
    _begin(state, tool)
    if state.market is None or state.signal is None or state.risk is None:
        raise PolicyViolationError("risk required before ml")
    gates_open = state.signal.gates_open_candidate and state.risk.approved
    ml = _roles().run_decision_ml_agent(
        {
            "features": state.market.features,
            "gates_open": gates_open,
            "model_mode": state.model_mode,
            "model_present": state.model is not None,
        },
        model=state.model,
    )
    state.ml = ml
    state.workflow.append(ml.step.as_workflow_dict())
    return _end(state, tool, ml.step.status, ml.step.note)


def handle_agent_run_knowledge(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> RoutingStepOut:
    del payload
    state = _state(context)
    tool = ToolId.AGENT_RUN_KNOWLEDGE
    _begin(state, tool)
    knowledge = _roles().run_knowledge_agent(
        KnowledgeAgentIn(facts=state.knowledge_facts(), citations=state.citations)
    )
    state.knowledge = knowledge
    state.workflow.append(knowledge.step.as_workflow_dict())
    return _end(state, tool, knowledge.step.status, knowledge.step.note)


def handle_workflow_finish(
    payload: RoutingEmptyIn,
    *,
    context: ToolContext | None = None,
) -> WorkflowFinishOut:
    del payload
    state = _state(context)
    tool = ToolId.WORKFLOW_FINISH
    _begin(state, tool)
    snapshot = state.build_snapshot()
    state.policy.mark_completed(tool)
    return WorkflowFinishOut(
        finished=True,
        action=snapshot.action.value,
        required_complete=state.policy.required_done(),
        completed_tools=sorted(t.value for t in state.policy.completed),
    )


def routing_handler_map() -> dict[ToolId, Any]:
    return {
        ToolId.AGENT_RUN_MARKET_DATA: handle_agent_run_market_data,
        ToolId.AGENT_RUN_VISION: handle_agent_run_vision,
        ToolId.AGENT_RUN_JOURNAL: handle_agent_run_journal,
        ToolId.AGENT_RUN_STRATEGY: handle_agent_run_strategy,
        ToolId.AGENT_RUN_SIGNAL: handle_agent_run_signal,
        ToolId.AGENT_RUN_RISK: handle_agent_run_risk,
        ToolId.AGENT_RUN_ML: handle_agent_run_ml,
        ToolId.AGENT_RUN_KNOWLEDGE: handle_agent_run_knowledge,
        ToolId.WORKFLOW_FINISH: handle_workflow_finish,
    }
