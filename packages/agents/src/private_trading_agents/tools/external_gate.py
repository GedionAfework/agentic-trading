"""Gate for SideEffect.EXTERNAL tools — off by default."""

from __future__ import annotations

from private_trading_agents.tools.context import ToolContext


def external_tools_enabled(context: ToolContext | None = None) -> bool:
    """EXTERNAL tools run only when explicitly enabled.

    Order:
    1. ToolContext.extras['external_tools_enabled'] if set (tests / request scope)
    2. Settings.agent_external_tools_enabled (default False)
    """
    if context is not None and "external_tools_enabled" in context.extras:
        return bool(context.extras["external_tools_enabled"])
    try:
        from private_trading_core.config import get_settings

        return bool(get_settings().agent_external_tools_enabled)
    except Exception:  # noqa: BLE001 — fail closed
        return False
