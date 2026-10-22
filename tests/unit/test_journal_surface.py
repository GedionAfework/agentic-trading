"""AG-08 journal product surface: read-only narrate, no trade authority."""

from __future__ import annotations

import pytest
from private_trading_agents.contracts import AgentId
from private_trading_agents.journal_surface import (
    JournalTradeAuthorityError,
    assert_journal_surface_permissions,
    run_journal_calibration_surface,
    run_journal_narrate_surface,
)
from private_trading_agents.tools import ToolId, has_permission
from private_trading_agents.tools.injection import assert_tool_policy_intact
from private_trading_analytics.metrics import SAMPLE_INSUFFICIENT
from private_trading_analytics.narrate import narrate_calibration, narrate_performance


def _snapshot() -> dict:
    return {
        "cohort": "paper",
        "strategy_code": "wyckoff-hdm",
        "instrument_symbol": "*",
        "timeframe": "*",
        "session_bucket": "*",
        "sample_size": 3,
        "sample_status": SAMPLE_INSUFFICIENT,
        "metrics": {
            "win_count": 2,
            "loss_count": 1,
            "win_rate": 0.6667,
            "mean_r": 0.5,
            "sum_r": 1.5,
        },
        "warnings": ["sample_size=3 is below 10; metrics are not decision-grade."],
    }


def test_journal_surface_narrates_without_trade_authority() -> None:
    snap = _snapshot()
    direct = narrate_performance(snap)
    result = run_journal_narrate_surface(snapshot=snap)
    assert result.authorizes_trade is False
    assert result.decision_action is None
    assert result.agent == "AG-08"
    assert result.narrative == direct
    assert result.tool_traces
    assert any(t["tool"] == "journal.narrate_performance" for t in result.tool_traces)
    assert result.meta()["authorizes_trade"] is False
    assert result.meta()["surface"] == "journal_ai"
    assert_tool_policy_intact()


def test_journal_calibration_surface_no_trade_authority() -> None:
    snap = {
        "cohort": "paper",
        "band_field": "confidence_band",
        "sample_size": 3,
        "sample_status": SAMPLE_INSUFFICIENT,
        "bands": {"low": {"sample_size": 3, "win_rate": 0.5, "mean_r": 0.1}},
        "drift_flags": [],
        "warnings": ["sample_size=3 is below 10; metrics are not decision-grade."],
    }
    direct = narrate_calibration(snap)
    result = run_journal_calibration_surface(snapshot=snap)
    assert result.authorizes_trade is False
    assert result.decision_action is None
    assert result.agent == "AG-08"
    assert result.narrative == direct
    assert result.tool == "journal.narrate_calibration"
    assert any(t["tool"] == "journal.narrate_calibration" for t in result.tool_traces)
    assert result.meta()["surface"] == "journal_ai"
    assert_tool_policy_intact()


def test_journal_surface_rejects_trade_tool_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    real = has_permission

    def _spoof(agent, tool):  # noqa: ANN001
        if agent == AgentId.AG08_JOURNAL and tool == ToolId.RISK_ASSESS:
            return True
        return real(agent, tool)

    monkeypatch.setattr(
        "private_trading_agents.journal_surface.has_permission",
        _spoof,
    )
    with pytest.raises(JournalTradeAuthorityError):
        assert_journal_surface_permissions()
