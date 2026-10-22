"""Least-privilege tool allowlist per agent.

Deny by default: an agent may only invoke tools listed here.
AG-01 orchestrates roles and holds zero tools.
AG-08 is a stub and holds zero tools.
No WRITE / EXTERNAL / EXECUTE tools are granted to anyone.
"""

from __future__ import annotations

from private_trading_agents.contracts import AgentId
from private_trading_agents.tools.ids import ToolId

# Frozen allowlists — edit deliberately; never grant by omission of a deny list.
AGENT_TOOL_ALLOWLIST: dict[AgentId, frozenset[ToolId]] = {
    AgentId.AG01_ORCHESTRATOR: frozenset(),
    AgentId.AG02_KNOWLEDGE: frozenset({ToolId.EXPLAIN_GROUNDED}),
    AgentId.AG03_VISION: frozenset({ToolId.VISION_CHECK_VERDICT}),
    AgentId.AG04_MARKET_DATA: frozenset({ToolId.FEATURES_COMPUTE}),
    AgentId.AG05_STRATEGY: frozenset({ToolId.STRATEGY_EVALUATE}),
    AgentId.AG06_RISK: frozenset({ToolId.RISK_ASSESS}),
    AgentId.AG07_SIGNAL: frozenset({ToolId.SIGNAL_CHECK_GATES}),
    AgentId.AG08_JOURNAL: frozenset(),
    AgentId.AG09_DECISION_ML: frozenset({ToolId.ML_RANK}),
}

# Side effects the runtime will execute. Everything else fails closed.
ALLOWED_SIDE_EFFECTS = frozenset({"none", "read"})


def allowed_tools(agent: AgentId) -> frozenset[ToolId]:
    return AGENT_TOOL_ALLOWLIST.get(agent, frozenset())


def has_permission(agent: AgentId, tool: ToolId) -> bool:
    return tool in allowed_tools(agent)


def permissions_matrix() -> dict[str, list[str]]:
    """Audit-friendly dump: agent id → sorted tool ids."""
    return {
        agent.value: sorted(tool.value for tool in tools)
        for agent, tools in sorted(
            AGENT_TOOL_ALLOWLIST.items(), key=lambda item: item[0].value
        )
    }
