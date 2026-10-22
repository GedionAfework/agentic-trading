"""Fail-closed policy graph for AG-01 routing tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from private_trading_core.errors import ForbiddenError

from private_trading_agents.tools.ids import ToolId

# Must complete before workflow.finish on any decision path.
REQUIRED_BEFORE_FINISH: frozenset[ToolId] = frozenset(
    {
        ToolId.AGENT_RUN_MARKET_DATA,
        ToolId.AGENT_RUN_STRATEGY,
        ToolId.AGENT_RUN_SIGNAL,
        ToolId.AGENT_RUN_RISK,
    }
)

# Optional routing tools AG-01 may call when prerequisites allow.
OPTIONAL_ROUTING: frozenset[ToolId] = frozenset(
    {
        ToolId.AGENT_RUN_VISION,
        ToolId.AGENT_RUN_JOURNAL,
        ToolId.AGENT_RUN_ML,
        ToolId.AGENT_RUN_KNOWLEDGE,
    }
)

ROUTING_TOOLS: frozenset[ToolId] = (
    REQUIRED_BEFORE_FINISH | OPTIONAL_ROUTING | frozenset({ToolId.WORKFLOW_FINISH})
)

# Prerequisites that must already be completed (empty = always ok to start).
_PREREQS: dict[ToolId, frozenset[ToolId]] = {
    ToolId.AGENT_RUN_MARKET_DATA: frozenset(),
    ToolId.AGENT_RUN_VISION: frozenset(),
    ToolId.AGENT_RUN_JOURNAL: frozenset(),
    ToolId.AGENT_RUN_STRATEGY: frozenset({ToolId.AGENT_RUN_MARKET_DATA}),
    ToolId.AGENT_RUN_SIGNAL: frozenset({ToolId.AGENT_RUN_STRATEGY}),
    ToolId.AGENT_RUN_RISK: frozenset({ToolId.AGENT_RUN_SIGNAL}),
    ToolId.AGENT_RUN_ML: frozenset({ToolId.AGENT_RUN_RISK}),
    ToolId.AGENT_RUN_KNOWLEDGE: frozenset({ToolId.AGENT_RUN_RISK}),
    ToolId.WORKFLOW_FINISH: REQUIRED_BEFORE_FINISH,
}


class PolicyViolationError(ForbiddenError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details=details or {})
        self.code = "POLICY_VIOLATION"


@dataclass(slots=True)
class PolicyGraph:
    """Tracks completed routing tools and denies illegal orders."""

    completed: set[ToolId] = field(default_factory=set)

    def missing_prereqs(self, tool: ToolId) -> frozenset[ToolId]:
        needed = _PREREQS.get(tool, frozenset())
        return frozenset(t for t in needed if t not in self.completed)

    def assert_can_invoke(self, tool: ToolId) -> None:
        if tool not in ROUTING_TOOLS:
            raise PolicyViolationError(
                f"Tool {tool.value} is not an AG-01 routing tool",
                details={"tool": tool.value},
            )
        if tool in self.completed and tool != ToolId.WORKFLOW_FINISH:
            raise PolicyViolationError(
                f"Routing tool already completed: {tool.value}",
                details={"tool": tool.value, "completed": sorted(t.value for t in self.completed)},
            )
        missing = self.missing_prereqs(tool)
        if missing:
            raise PolicyViolationError(
                f"Cannot invoke {tool.value}; missing {sorted(t.value for t in missing)}",
                details={
                    "tool": tool.value,
                    "missing": sorted(t.value for t in missing),
                    "completed": sorted(t.value for t in self.completed),
                },
            )

    def mark_completed(self, tool: ToolId) -> None:
        if tool != ToolId.WORKFLOW_FINISH:
            self.completed.add(tool)

    def required_done(self) -> bool:
        return REQUIRED_BEFORE_FINISH.issubset(self.completed)
