"""Tool invocation failures — fail closed."""

from __future__ import annotations

from typing import Any

from private_trading_core.errors import AppError, ForbiddenError


class UnknownToolError(AppError):
    def __init__(self, tool: str, **kwargs: Any) -> None:
        super().__init__(
            "UNKNOWN_TOOL",
            f"Tool is not registered: {tool}",
            details={"tool": tool},
            **kwargs,
        )


class ToolPermissionError(ForbiddenError):
    def __init__(self, *, agent: str, tool: str, **kwargs: Any) -> None:
        super().__init__(
            f"Agent {agent} is not permitted to invoke {tool}",
            details={"agent": agent, "tool": tool, "policy": "least_privilege"},
            **kwargs,
        )
        self.code = "TOOL_PERMISSION_DENIED"


class SideEffectDeniedError(ForbiddenError):
    def __init__(self, *, tool: str, side_effect: str, **kwargs: Any) -> None:
        super().__init__(
            f"Tool {tool} side-effect '{side_effect}' is blocked by policy",
            details={
                "tool": tool,
                "side_effect": side_effect,
                "policy": "least_privilege",
            },
            **kwargs,
        )
        self.code = "TOOL_SIDE_EFFECT_DENIED"
