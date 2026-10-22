"""Step 1 agent runtime: budgets + tool traces."""

from __future__ import annotations

import pytest
from private_trading_agents.agent_runtime import (
    AgentBudget,
    BudgetExceededError,
    agent_session,
    call_tool,
)
from private_trading_agents.contracts import AgentId
from private_trading_agents.tools import ToolId, ToolPermissionError
from private_trading_agents.workflow import DecisionAction, run_decision_workflow
from private_trading_backtest.fixtures import (
    FIXTURE_RETEST_INDEX,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)


def test_workflow_attaches_ok_tool_traces_without_changing_action() -> None:
    bars = frozen_bos_long_fixture()
    snapshot = run_decision_workflow(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=19,
    )
    assert snapshot.action == DecisionAction.NO_SETUP
    assert snapshot.tool_traces
    assert snapshot.evidence.get("agent_runtime") == "v1"
    assert snapshot.evidence.get("tool_traces") == snapshot.tool_traces

    by_agent = {row["agent"]: row for row in snapshot.tool_traces}
    assert by_agent["AG-04"]["tool"] == "features.compute"
    assert by_agent["AG-04"]["status"] == "ok"
    assert by_agent["AG-05"]["tool"] == "strategy.evaluate"
    assert by_agent["AG-06"]["tool"] == "risk.assess"
    assert by_agent["AG-07"]["tool"] == "signal.check_gates"
    assert by_agent["AG-02"]["tool"] == "explain.grounded"
    assert by_agent["AG-03"]["tool"] == "vision.check_verdict"
    assert by_agent["AG-09"]["tool"] == "ml.rank"
    assert all(row["status"] == "ok" for row in snapshot.tool_traces)
    assert "AG-01" not in by_agent  # orchestrator has zero tools
    assert "AG-08" not in by_agent or by_agent.get("AG-08") is None


def test_stale_path_still_waits_with_traces() -> None:
    snapshot = run_decision_workflow(
        frozen_bos_long_fixture(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=FIXTURE_RETEST_INDEX,
        data_fresh=False,
    )
    assert snapshot.action == DecisionAction.WAIT
    assert "stale_market_data" in snapshot.hard_blockers
    assert len(snapshot.tool_traces) >= 6


def test_denied_cross_agent_call_is_traced() -> None:
    with agent_session() as session:
        with pytest.raises(ToolPermissionError):
            call_tool(
                agent=AgentId.AG05_STRATEGY,
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
        assert len(session.traces) == 1
        trace = session.traces[0]
        assert trace.status == "denied"
        assert trace.code == "TOOL_PERMISSION_DENIED"
        assert trace.agent == "AG-05"
        assert trace.tool == "features.compute"


def test_budget_max_tool_calls_is_enforced() -> None:
    with agent_session(
        budgets={AgentId.AG03_VISION: AgentBudget(max_tool_calls=1)}
    ) as session:
        call_tool(
            agent=AgentId.AG03_VISION,
            tool=ToolId.VISION_CHECK_VERDICT,
            payload={"attached": False},
        )
        with pytest.raises(BudgetExceededError) as exc:
            call_tool(
                agent=AgentId.AG03_VISION,
                tool=ToolId.VISION_CHECK_VERDICT,
                payload={"attached": False},
            )
        assert exc.value.code == "AGENT_BUDGET_EXCEEDED"
        assert session.traces[-1].status == "budget_exceeded"
