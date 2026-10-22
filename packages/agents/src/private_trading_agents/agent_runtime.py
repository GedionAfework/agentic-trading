"""Per-agent runtime: budgets + traced tool calls (Step 1 toward agentic loops).

Roles call tools only through this layer when a session is active. Decisions stay
deterministic; traces make every gated invoke auditable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Literal

from private_trading_core.errors import AppError
from pydantic import BaseModel

from private_trading_agents.contracts import AgentId
from private_trading_agents.tools.errors import (
    SideEffectDeniedError,
    ToolPermissionError,
    UnknownToolError,
)
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.runtime import ToolContext, invoke_tool

TraceStatus = Literal["ok", "denied", "error", "budget_exceeded"]


class BudgetExceededError(AppError):
    def __init__(self, *, agent: str, limit: str, **kwargs: Any) -> None:
        super().__init__(
            "AGENT_BUDGET_EXCEEDED",
            f"Agent {agent} exceeded {limit}",
            details={"agent": agent, "limit": limit, "policy": "least_privilege"},
            **kwargs,
        )


@dataclass(frozen=True, slots=True)
class AgentBudget:
    """Per-agent caps. Step 1 uses low defaults (one tool per role today)."""

    max_tool_calls: int = 8
    max_wall_ms: float = 30_000.0


@dataclass(frozen=True, slots=True)
class ToolTrace:
    agent: str
    tool: str
    status: TraceStatus
    duration_ms: float
    step: int
    code: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentRuntime:
    """Bound to one AgentId inside a session — enforce budget + record traces."""

    session: AgentSession
    agent: AgentId
    budget: AgentBudget
    _calls: int = 0
    _wall_ms: float = 0.0

    def invoke(
        self,
        tool: ToolId | str,
        payload: BaseModel | dict[str, Any],
        *,
        context: ToolContext | None = None,
        note: str = "",
    ) -> BaseModel:
        tool_name = tool.value if isinstance(tool, ToolId) else str(tool)
        if self._calls >= self.budget.max_tool_calls:
            self.session.record(
                ToolTrace(
                    agent=self.agent.value,
                    tool=tool_name,
                    status="budget_exceeded",
                    duration_ms=0.0,
                    step=self._calls + 1,
                    code="AGENT_BUDGET_EXCEEDED",
                    note="max_tool_calls",
                )
            )
            raise BudgetExceededError(agent=self.agent.value, limit="max_tool_calls")
        if self._wall_ms >= self.budget.max_wall_ms:
            self.session.record(
                ToolTrace(
                    agent=self.agent.value,
                    tool=tool_name,
                    status="budget_exceeded",
                    duration_ms=0.0,
                    step=self._calls + 1,
                    code="AGENT_BUDGET_EXCEEDED",
                    note="max_wall_ms",
                )
            )
            raise BudgetExceededError(agent=self.agent.value, limit="max_wall_ms")

        started = perf_counter()
        try:
            result = invoke_tool(
                agent=self.agent,
                tool=tool,
                payload=payload,
                context=context,
            )
        except (ToolPermissionError, UnknownToolError, SideEffectDeniedError) as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._calls += 1
            self._wall_ms += duration_ms
            self.session.record(
                ToolTrace(
                    agent=self.agent.value,
                    tool=tool_name,
                    status="denied",
                    duration_ms=round(duration_ms, 3),
                    step=self._calls,
                    code=getattr(exc, "code", None),
                    note=note or str(exc),
                )
            )
            raise
        except Exception as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._calls += 1
            self._wall_ms += duration_ms
            self.session.record(
                ToolTrace(
                    agent=self.agent.value,
                    tool=tool_name,
                    status="error",
                    duration_ms=round(duration_ms, 3),
                    step=self._calls,
                    code=type(exc).__name__,
                    note=note or str(exc)[:200],
                )
            )
            raise
        else:
            duration_ms = (perf_counter() - started) * 1000.0
            self._calls += 1
            self._wall_ms += duration_ms
            self.session.record(
                ToolTrace(
                    agent=self.agent.value,
                    tool=tool_name,
                    status="ok",
                    duration_ms=round(duration_ms, 3),
                    step=self._calls,
                    code=None,
                    note=note,
                )
            )
            return result


@dataclass(slots=True)
class AgentSession:
    """Workflow-scoped session collecting tool traces across agents."""

    default_budget: AgentBudget = field(default_factory=AgentBudget)
    budgets: dict[AgentId, AgentBudget] = field(default_factory=dict)
    traces: list[ToolTrace] = field(default_factory=list)
    _runtimes: dict[AgentId, AgentRuntime] = field(default_factory=dict)

    def runtime(self, agent: AgentId) -> AgentRuntime:
        existing = self._runtimes.get(agent)
        if existing is not None:
            return existing
        budget = self.budgets.get(agent, self.default_budget)
        created = AgentRuntime(session=self, agent=agent, budget=budget)
        self._runtimes[agent] = created
        return created

    def record(self, trace: ToolTrace) -> None:
        self.traces.append(trace)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [trace.as_dict() for trace in self.traces]


_SESSION: ContextVar[AgentSession | None] = ContextVar(
    "private_trading_agent_session", default=None
)


def current_session() -> AgentSession | None:
    return _SESSION.get()


@contextmanager
def agent_session(
    *,
    default_budget: AgentBudget | None = None,
    budgets: dict[AgentId, AgentBudget] | None = None,
) -> Iterator[AgentSession]:
    session = AgentSession(
        default_budget=default_budget or AgentBudget(),
        budgets=budgets or {},
    )
    token: Token = _SESSION.set(session)
    try:
        yield session
    finally:
        _SESSION.reset(token)


def call_tool(
    *,
    agent: AgentId,
    tool: ToolId | str,
    payload: BaseModel | dict[str, Any],
    context: ToolContext | None = None,
    note: str = "",
) -> BaseModel:
    """Invoke a tool under the active session (traced) or bare gate (no session)."""
    session = current_session()
    if session is None:
        return invoke_tool(agent=agent, tool=tool, payload=payload, context=context)
    return session.runtime(agent).invoke(tool, payload, context=context, note=note)
