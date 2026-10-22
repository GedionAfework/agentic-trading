"""AG-08 journal agent: read-only metrics + narration."""

from __future__ import annotations

import pytest
from private_trading_agents.contracts import AgentId
from private_trading_agents.roles import run_journal_agent
from private_trading_agents.tools import (
    ToolId,
    ToolPermissionError,
    has_permission,
    invoke_tool,
)


def _trades() -> list[dict]:
    return [
        {
            "strategy_code": "wyckoff-hdm",
            "instrument_symbol": "BTCUSDT",
            "timeframe": "1h",
            "session_bucket": "europe",
            "direction": "long",
            "exit_reason": "target",
            "realized_r": 2.0,
            "realized_pnl": 100.0,
            "won": True,
        },
        {
            "strategy_code": "wyckoff-hdm",
            "instrument_symbol": "BTCUSDT",
            "timeframe": "1h",
            "session_bucket": "europe",
            "direction": "long",
            "exit_reason": "stop",
            "realized_r": -1.0,
            "realized_pnl": -50.0,
            "won": False,
        },
    ]


def test_journal_skipped_when_disabled() -> None:
    out = run_journal_agent({"enabled": False})
    assert out.step.status == "skipped"
    assert out.authorizes_trade is False
    assert out.narrative is None


def test_journal_summarize_and_narrate_via_role() -> None:
    out = run_journal_agent(
        {
            "enabled": True,
            "cohort": "paper",
            "trades": _trades(),
            "strategy_code": "wyckoff-hdm",
        }
    )
    assert out.step.agent == AgentId.AG08_JOURNAL
    assert out.step.status == "ok"
    assert out.authorizes_trade is False
    assert out.sample_size == 2
    assert out.cohort == "paper"
    assert out.narrative is not None
    assert "paper" in out.narrative
    assert "never merged" in out.narrative


def test_journal_tools_are_ag08_only() -> None:
    assert has_permission(AgentId.AG08_JOURNAL, ToolId.JOURNAL_SUMMARIZE_METRICS)
    assert not has_permission(AgentId.AG05_STRATEGY, ToolId.JOURNAL_SUMMARIZE_METRICS)
    assert not has_permission(AgentId.AG01_ORCHESTRATOR, ToolId.JOURNAL_NARRATE_PERFORMANCE)
    with pytest.raises(ToolPermissionError):
        invoke_tool(
            agent=AgentId.AG06_RISK,
            tool=ToolId.JOURNAL_NARRATE_PERFORMANCE,
            payload={
                "snapshot": {
                    "cohort": "paper",
                    "sample_size": 0,
                    "sample_status": "insufficient_sample",
                    "metrics": {},
                    "warnings": [],
                    "strategy_code": "*",
                    "instrument_symbol": "*",
                    "timeframe": "*",
                    "session_bucket": "*",
                }
            },
        )


def test_journal_does_not_merge_cohorts_flag() -> None:
    out = invoke_tool(
        agent=AgentId.AG08_JOURNAL,
        tool=ToolId.JOURNAL_SUMMARIZE_METRICS,
        payload={"cohort": "paper", "trades": _trades()},
    )
    assert out.merges_cohorts is False
    assert out.cohort == "paper"


def test_ag08_cannot_call_trade_tools() -> None:
    for tool in (
        ToolId.RISK_ASSESS,
        ToolId.STRATEGY_EVALUATE,
        ToolId.WORKFLOW_FINISH,
        ToolId.FEATURES_COMPUTE,
    ):
        assert not has_permission(AgentId.AG08_JOURNAL, tool)
        with pytest.raises(ToolPermissionError):
            invoke_tool(agent=AgentId.AG08_JOURNAL, tool=tool, payload={})
