"""Allowlisted agent tools with least-privilege permissions."""

from private_trading_agents.tools.catalog import TOOL_CATALOG, catalog_summary, get_tool
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.errors import (
    SideEffectDeniedError,
    ToolPermissionError,
    UnknownToolError,
)
from private_trading_agents.tools.external_gate import external_tools_enabled
from private_trading_agents.tools.ids import SideEffect, ToolId
from private_trading_agents.tools.permissions import (
    AGENT_TOOL_ALLOWLIST,
    allowed_side_effects,
    allowed_tools,
    has_permission,
    permissions_matrix,
)
from private_trading_agents.tools.policy import (
    REQUIRED_BEFORE_FINISH,
    PolicyGraph,
    PolicyViolationError,
)
from private_trading_agents.tools.runtime import (
    ToolInvocation,
    assert_tool_registered,
    invoke_tool,
    registered_tool_ids,
)

__all__ = [
    "AGENT_TOOL_ALLOWLIST",
    "REQUIRED_BEFORE_FINISH",
    "TOOL_CATALOG",
    "PolicyGraph",
    "PolicyViolationError",
    "SideEffect",
    "SideEffectDeniedError",
    "ToolContext",
    "ToolId",
    "ToolInvocation",
    "ToolPermissionError",
    "UnknownToolError",
    "allowed_side_effects",
    "allowed_tools",
    "assert_tool_registered",
    "catalog_summary",
    "external_tools_enabled",
    "get_tool",
    "has_permission",
    "invoke_tool",
    "permissions_matrix",
    "registered_tool_ids",
]
