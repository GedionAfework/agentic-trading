"""Allowlisted agent tools with least-privilege permissions."""

from private_trading_agents.tools.catalog import TOOL_CATALOG, catalog_summary, get_tool
from private_trading_agents.tools.errors import (
    SideEffectDeniedError,
    ToolPermissionError,
    UnknownToolError,
)
from private_trading_agents.tools.ids import SideEffect, ToolId
from private_trading_agents.tools.permissions import (
    AGENT_TOOL_ALLOWLIST,
    allowed_tools,
    has_permission,
    permissions_matrix,
)
from private_trading_agents.tools.runtime import (
    ToolContext,
    ToolInvocation,
    assert_tool_registered,
    invoke_tool,
    registered_tool_ids,
)

__all__ = [
    "AGENT_TOOL_ALLOWLIST",
    "TOOL_CATALOG",
    "SideEffect",
    "SideEffectDeniedError",
    "ToolContext",
    "ToolId",
    "ToolInvocation",
    "ToolPermissionError",
    "UnknownToolError",
    "allowed_tools",
    "assert_tool_registered",
    "catalog_summary",
    "get_tool",
    "has_permission",
    "invoke_tool",
    "permissions_matrix",
    "registered_tool_ids",
]
