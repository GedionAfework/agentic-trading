"""Agentic ops status — flags for soak / Ask / planner (read-only)."""

from __future__ import annotations

from typing import Any


def agentic_ops_status() -> dict[str, Any]:
    """Snapshot of agentic feature flags and safe defaults."""
    try:
        from private_trading_core.config import get_settings

        settings = get_settings()
        external = bool(settings.agent_external_tools_enabled)
        shadow = bool(settings.agentic_shadow_enabled)
        llm_planner = bool(settings.agentic_llm_planner_enabled)
    except Exception:  # noqa: BLE001
        external = False
        shadow = False
        llm_planner = False

    return {
        "agent_external_tools_enabled": external,
        "agentic_shadow_enabled": shadow,
        "agentic_llm_planner_enabled": llm_planner,
        "notes": {
            "shadow": (
                "Set AGENTIC_SHADOW_ENABLED=true for paper soak parity traces. "
                "Never overrides deterministic ENTER/paper opens."
            ),
            "external": (
                "Ask AI request-scopes EXTERNAL for knowledge.ask. "
                "Global AGENT_EXTERNAL_TOOLS_ENABLED remains off by default."
            ),
            "llm_planner": (
                "AGENTIC_LLM_PLANNER_ENABLED alone keeps the fixed plan unless a "
                "planner bridge is injected into run_agentic_orchestrator."
            ),
        },
        "env_keys": [
            "AGENT_EXTERNAL_TOOLS_ENABLED",
            "AGENTIC_SHADOW_ENABLED",
            "AGENTIC_LLM_PLANNER_ENABLED",
        ],
    }
