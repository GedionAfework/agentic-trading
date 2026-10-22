"""Agentic ops status helper — flag snapshot for soak."""

from __future__ import annotations

from private_trading_agents.ops_status import agentic_ops_status


def test_ops_status_defaults_off() -> None:
    status = agentic_ops_status()
    assert status["agent_external_tools_enabled"] is False
    assert status["agentic_shadow_enabled"] is False
    assert status["agentic_llm_planner_enabled"] is False
    assert "AGENTIC_SHADOW_ENABLED" in status["env_keys"]
    assert "shadow" in status["notes"]
    assert "Never overrides" in status["notes"]["shadow"]
