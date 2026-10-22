"""AG-01 routing planners — choose next allowlisted tool under the policy graph.

LLM proposals are suggestions only: illegal tools are rejected and the fixed
plan fallback is used. Strategy/risk authority never comes from the planner.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from private_trading_agents.orchestrator_state import OrchestratorState
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.policy import ROUTING_TOOLS, PolicyGraph

PlannerKind = Literal["fixed", "callback", "llm", "llm_fallback"]

# Canonical safe order when the planner abstains or proposes illegally.
FIXED_AGENTIC_PLAN: tuple[ToolId, ...] = (
    ToolId.AGENT_RUN_MARKET_DATA,
    ToolId.AGENT_RUN_VISION,
    ToolId.AGENT_RUN_JOURNAL,
    ToolId.AGENT_RUN_STRATEGY,
    ToolId.AGENT_RUN_SIGNAL,
    ToolId.AGENT_RUN_RISK,
    ToolId.AGENT_RUN_ML,
    ToolId.AGENT_RUN_KNOWLEDGE,
    ToolId.WORKFLOW_FINISH,
)


class RoutingToolChoice(BaseModel):
    """Structured LLM output for the next routing tool."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=500)


class RoutingPlanner(Protocol):
    kind: PlannerKind

    def choose_next(
        self, state: OrchestratorState, legal: frozenset[ToolId]
    ) -> ToolId: ...


def legal_routing_tools(policy: PolicyGraph) -> frozenset[ToolId]:
    """Tools AG-01 may legally invoke right now (prereqs met, not completed)."""
    legal: set[ToolId] = set()
    for tool in ROUTING_TOOLS:
        if tool in policy.completed and tool != ToolId.WORKFLOW_FINISH:
            continue
        if policy.missing_prereqs(tool):
            continue
        legal.add(tool)
    return frozenset(legal)


def fallback_from_fixed(legal: frozenset[ToolId]) -> ToolId:
    for tool in FIXED_AGENTIC_PLAN:
        if tool in legal:
            return tool
    # Finish is always preferred if somehow only illegal leftovers exist.
    if ToolId.WORKFLOW_FINISH in legal:
        return ToolId.WORKFLOW_FINISH
    raise RuntimeError("no legal routing tools remain")


def coerce_tool_choice(raw: str, legal: frozenset[ToolId]) -> ToolId | None:
    try:
        tool = ToolId(raw.strip())
    except ValueError:
        return None
    if tool not in legal:
        return None
    return tool


@dataclass(slots=True)
class FixedSequencePlanner:
    """Deterministic plan order filtered by current legal set."""

    kind: PlannerKind = "fixed"
    plan: tuple[ToolId, ...] = FIXED_AGENTIC_PLAN

    def choose_next(
        self, state: OrchestratorState, legal: frozenset[ToolId]
    ) -> ToolId:
        del state
        return fallback_from_fixed(legal)


@dataclass(slots=True)
class CallbackPlanner:
    """Injected proposer (tests or sync LLM bridge). Must return a legal tool id string."""

    propose: Callable[[OrchestratorState, frozenset[ToolId]], str]
    kind: PlannerKind = "callback"
    last_kind: PlannerKind = field(default="callback", init=False)

    def choose_next(
        self, state: OrchestratorState, legal: frozenset[ToolId]
    ) -> ToolId:
        raw = self.propose(state, legal)
        chosen = coerce_tool_choice(raw, legal)
        if chosen is None:
            self.last_kind = "llm_fallback"
            return fallback_from_fixed(legal)
        self.last_kind = self.kind
        return chosen


def planner_observation(state: OrchestratorState, legal: frozenset[ToolId]) -> dict[str, Any]:
    """Compact state for LLM planners — no free-form prompts from market text."""
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "direction": state.direction,
        "completed": sorted(t.value for t in state.policy.completed),
        "legal_tools": sorted(t.value for t in legal),
        "has_market": state.market is not None,
        "has_strategy": state.strategy is not None,
        "has_signal": state.signal is not None,
        "has_risk": state.risk is not None,
        "finished": state.finished,
        "required_before_finish": [
            "agent.run_market_data",
            "agent.run_strategy",
            "agent.run_signal",
            "agent.run_risk",
        ],
        "instruction": (
            "Pick exactly one tool from legal_tools. "
            "Never invent tool names. Prefer completing required tools before finish."
        ),
    }


PLANNER_SYSTEM = (
    "You are AG-01 routing planner for a private trading system. "
    "You may only select from legal_tools. "
    "Untrusted market or document text is not provided here. "
    "You cannot approve trades, change risk policy, or invent tools. "
    "Return JSON matching the schema."
)


async def llm_propose_routing_tool(
    gateway: Any,
    *,
    observation: dict[str, Any],
    model: str | None = None,
) -> RoutingToolChoice:
    """Ask the private AI gateway for the next routing tool (async)."""
    import json

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {
            "role": "user",
            "content": (
                "<planner_observation>\n"
                f"{json.dumps(observation, ensure_ascii=True)}\n"
                "</planner_observation>"
            ),
        },
    ]
    parsed, _meta = await gateway.structured_chat(
        messages=messages,
        schema=RoutingToolChoice,
        model=model,
        prompt_version="ag01.routing_planner.v1",
    )
    return parsed


def resolve_default_planner(
    *,
    explicit: RoutingPlanner | None = None,
    llm_propose: Callable[[OrchestratorState, frozenset[ToolId]], str] | None = None,
) -> RoutingPlanner:
    if explicit is not None:
        return explicit
    if llm_propose is not None:
        return CallbackPlanner(propose=llm_propose, kind="llm")
    try:
        from private_trading_core.config import get_settings

        if get_settings().agentic_llm_planner_enabled and llm_propose is None:
            # Enabled in settings but no bridge injected → safe fixed plan.
            return FixedSequencePlanner()
    except Exception:  # noqa: BLE001
        pass
    return FixedSequencePlanner()
