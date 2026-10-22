"""AG-01 routing planner: legal tools + LLM proposal fail-closed."""

from __future__ import annotations

from private_trading_agents.agent_runtime import agent_session
from private_trading_agents.contracts import AgentId
from private_trading_agents.orchestrator import ag01_budget, run_agentic_orchestrator
from private_trading_agents.planner import (
    CallbackPlanner,
    FixedSequencePlanner,
    coerce_tool_choice,
    fallback_from_fixed,
    legal_routing_tools,
)
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.policy import PolicyGraph
from private_trading_agents.workflow import DecisionAction
from private_trading_backtest.fixtures import (
    FIXTURE_BOS_INDEX,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)


def test_legal_tools_start_with_market_and_optionals() -> None:
    legal = legal_routing_tools(PolicyGraph())
    assert ToolId.AGENT_RUN_MARKET_DATA in legal
    assert ToolId.AGENT_RUN_VISION in legal
    assert ToolId.AGENT_RUN_STRATEGY not in legal
    assert ToolId.WORKFLOW_FINISH not in legal


def test_illegal_llm_proposal_falls_back() -> None:
    legal = frozenset({ToolId.AGENT_RUN_MARKET_DATA, ToolId.AGENT_RUN_VISION})
    assert coerce_tool_choice("risk.assess", legal) is None
    assert coerce_tool_choice("agent.run_strategy", legal) is None
    assert fallback_from_fixed(legal) == ToolId.AGENT_RUN_MARKET_DATA


def test_callback_planner_fallback_on_bad_proposal() -> None:
    def _evil(_state, _legal):  # noqa: ANN001
        return "broker.place_order"

    planner = CallbackPlanner(propose=_evil, kind="llm")
    bars = frozen_bos_long_fixture()
    with agent_session(budgets={AgentId.AG01_ORCHESTRATOR: ag01_budget()}):
        snap = run_agentic_orchestrator(
            bars,
            symbol=FIXTURE_SYMBOL,
            timeframe=FIXTURE_TIMEFRAME,
            bar_index=FIXTURE_BOS_INDEX,
            planner=planner,
        )
    assert snap.action == DecisionAction.ENTER
    assert snap.evidence["planner"]["kind"] == "llm"
    steps = snap.evidence["planner"]["steps"]
    assert any("forced_fallback" in s or "llm_fallback" in s for s in steps)


def test_fixed_planner_still_parity() -> None:
    bars = frozen_bos_long_fixture()
    with agent_session(budgets={AgentId.AG01_ORCHESTRATOR: ag01_budget()}):
        snap = run_agentic_orchestrator(
            bars,
            symbol=FIXTURE_SYMBOL,
            timeframe=FIXTURE_TIMEFRAME,
            bar_index=19,
            planner=FixedSequencePlanner(),
        )
    assert snap.action == DecisionAction.NO_SETUP
    assert snap.evidence["planner"]["kind"] == "fixed"
