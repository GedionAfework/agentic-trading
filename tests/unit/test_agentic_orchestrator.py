"""AG-01 routing tools + policy graph (Step 2)."""

from __future__ import annotations

import pytest
from private_trading_agents.agent_runtime import agent_session, call_tool
from private_trading_agents.contracts import AgentId
from private_trading_agents.orchestrator import ag01_budget, run_agentic_orchestrator
from private_trading_agents.orchestrator_state import OrchestratorState
from private_trading_agents.tools import (
    PolicyViolationError,
    ToolId,
    ToolPermissionError,
)
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.policy import PolicyGraph
from private_trading_agents.workflow import DecisionAction, run_decision_workflow
from private_trading_backtest.fixtures import (
    FIXTURE_BOS_INDEX,
    FIXTURE_RETEST_INDEX,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)


def _bars():
    return frozen_bos_long_fixture()


def test_agentic_matches_deterministic_actions() -> None:
    bars = _bars()
    cases = [
        {"bar_index": 19},
        {"bar_index": FIXTURE_RETEST_INDEX, "data_fresh": False},
        {"bar_index": FIXTURE_BOS_INDEX},
        {"bar_index": 19, "position_state": "open"},
    ]
    for kwargs in cases:
        det = run_decision_workflow(
            bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, mode="deterministic", **kwargs
        )
        ag = run_decision_workflow(
            bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, mode="agentic", **kwargs
        )
        assert ag.action == det.action, kwargs
        assert ag.setup_state == det.setup_state
        assert ag.risk_approved == det.risk_approved
        assert ag.hard_blockers == det.hard_blockers
        assert ag.evidence["orchestrator_mode"] == "agentic"
        routing = [
            t for t in ag.tool_traces if t["agent"] == "AG-01" and t["status"] == "ok"
        ]
        assert any(t["tool"] == "agent.run_market_data" for t in routing)
        assert any(t["tool"] == "workflow.finish" for t in routing)


def test_policy_denies_strategy_before_market_data() -> None:
    graph = PolicyGraph()
    with pytest.raises(PolicyViolationError) as exc:
        graph.assert_can_invoke(ToolId.AGENT_RUN_STRATEGY)
    assert exc.value.code == "POLICY_VIOLATION"


def test_policy_denies_finish_without_required() -> None:
    graph = PolicyGraph()
    graph.mark_completed(ToolId.AGENT_RUN_MARKET_DATA)
    with pytest.raises(PolicyViolationError):
        graph.assert_can_invoke(ToolId.WORKFLOW_FINISH)


def test_illegal_route_is_traced_as_denied() -> None:
    bars = _bars()
    state = OrchestratorState(
        bars=bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=19,
        direction="long",
        data_fresh=True,
        market_actionable=True,
        position_state="flat",
        citations=[],
        min_rr="2.0",
        asset_class="crypto",
        model=None,
        model_id=None,
        model_mode=None,
        vision_in=None,
    )
    context = ToolContext(extras={"orchestrator_state": state})
    with agent_session(budgets={AgentId.AG01_ORCHESTRATOR: ag01_budget()}) as session:
        with pytest.raises(PolicyViolationError):
            call_tool(
                agent=AgentId.AG01_ORCHESTRATOR,
                tool=ToolId.AGENT_RUN_STRATEGY,
                payload={},
                context=context,
            )
        assert session.traces[-1].status == "denied"
        assert session.traces[-1].code == "POLICY_VIOLATION"


def test_ag01_still_cannot_call_features_compute() -> None:
    with pytest.raises(ToolPermissionError):
        call_tool(
            agent=AgentId.AG01_ORCHESTRATOR,
            tool=ToolId.FEATURES_COMPUTE,
            payload={
                "bars": [
                    {
                        "open_time": "2020-01-01T00:00:00Z",
                        "open": "1",
                        "high": "1",
                        "low": "1",
                        "close": "1",
                    }
                ]
            },
        )


def test_default_mode_is_deterministic() -> None:
    snapshot = run_decision_workflow(
        _bars(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=19,
    )
    assert snapshot.evidence["orchestrator_mode"] == "deterministic"
    assert snapshot.action == DecisionAction.NO_SETUP
    assert not any(t["tool"].startswith("agent.") for t in snapshot.tool_traces)


def test_run_agentic_orchestrator_direct() -> None:
    with agent_session(budgets={AgentId.AG01_ORCHESTRATOR: ag01_budget()}):
        snapshot = run_agentic_orchestrator(
            _bars(),
            symbol=FIXTURE_SYMBOL,
            timeframe=FIXTURE_TIMEFRAME,
            bar_index=FIXTURE_BOS_INDEX,
        )
    assert snapshot.action == DecisionAction.ENTER
    assert snapshot.risk_approved is True
