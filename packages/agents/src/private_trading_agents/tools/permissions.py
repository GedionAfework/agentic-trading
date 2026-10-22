"""Least-privilege tool allowlist per agent.

Deny by default: an agent may only invoke tools listed here.
AG-01 gets routing tools only — never specialist compute engines.
AG-08 is a stub and holds zero tools.
EXTERNAL tools are listed for AG-02/AG-03 but still gated by the enable flag.
The allowlist is frozen at import — runtime mutation is a policy tamper.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from private_trading_agents.contracts import AgentId
from private_trading_agents.tools.ids import ToolId

_AG01_ROUTING = frozenset(
    {
        ToolId.AGENT_RUN_MARKET_DATA,
        ToolId.AGENT_RUN_VISION,
        ToolId.AGENT_RUN_JOURNAL,
        ToolId.AGENT_RUN_STRATEGY,
        ToolId.AGENT_RUN_SIGNAL,
        ToolId.AGENT_RUN_RISK,
        ToolId.AGENT_RUN_ML,
        ToolId.AGENT_RUN_KNOWLEDGE,
        ToolId.WORKFLOW_FINISH,
    }
)

_AG02_TOOLS = frozenset(
    {
        ToolId.EXPLAIN_GROUNDED,
        ToolId.KNOWLEDGE_RETRIEVE,
        ToolId.KNOWLEDGE_ASK,
        ToolId.LLM_NARRATE_FACTS,
    }
)
_AG03_TOOLS = frozenset(
    {
        ToolId.VISION_CHECK_VERDICT,
        ToolId.VISION_EXTRACT,
    }
)

_RAW_ALLOWLIST: dict[AgentId, frozenset[ToolId]] = {
    AgentId.AG01_ORCHESTRATOR: _AG01_ROUTING,
    AgentId.AG02_KNOWLEDGE: _AG02_TOOLS,
    AgentId.AG03_VISION: _AG03_TOOLS,
    AgentId.AG04_MARKET_DATA: frozenset({ToolId.FEATURES_COMPUTE}),
    AgentId.AG05_STRATEGY: frozenset({ToolId.STRATEGY_EVALUATE}),
    AgentId.AG06_RISK: frozenset({ToolId.RISK_ASSESS}),
    AgentId.AG07_SIGNAL: frozenset({ToolId.SIGNAL_CHECK_GATES}),
    AgentId.AG08_JOURNAL: frozenset(),
    AgentId.AG09_DECISION_ML: frozenset({ToolId.ML_RANK}),
}

# Frozen — injection / untrusted code paths must not grant tools at runtime.
AGENT_TOOL_ALLOWLIST: Mapping[AgentId, frozenset[ToolId]] = MappingProxyType(
    dict(_RAW_ALLOWLIST)
)

# Base side effects always allowed. EXTERNAL requires an explicit enable flag.
ALLOWED_SIDE_EFFECTS = frozenset({"none", "read"})
EXTERNAL_SIDE_EFFECT = "external"


def allowed_tools(agent: AgentId) -> frozenset[ToolId]:
    return AGENT_TOOL_ALLOWLIST.get(agent, frozenset())


def has_permission(agent: AgentId, tool: ToolId) -> bool:
    return tool in allowed_tools(agent)


def allowed_side_effects(*, external_enabled: bool = False) -> frozenset[str]:
    if external_enabled:
        return ALLOWED_SIDE_EFFECTS | {EXTERNAL_SIDE_EFFECT}
    return ALLOWED_SIDE_EFFECTS


def permissions_matrix() -> dict[str, list[str]]:
    """Audit-friendly dump: agent id → sorted tool ids."""
    return {
        agent.value: sorted(tool.value for tool in tools)
        for agent, tools in sorted(
            AGENT_TOOL_ALLOWLIST.items(), key=lambda item: item[0].value
        )
    }
