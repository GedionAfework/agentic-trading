"""AG-01 agentic orchestrator — routing tools under a policy graph."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from private_trading_decision.predict import LoadedModel
from private_trading_features.types import CandleBar

from private_trading_agents.adapters import candles_to_models
from private_trading_agents.agent_runtime import AgentBudget, call_tool
from private_trading_agents.contracts import (
    AgentId,
    CitationModel,
    OrchestratorAgentIn,
    VisionAgentIn,
)
from private_trading_agents.orchestrator_state import OrchestratorState
from private_trading_agents.planner import (
    FIXED_AGENTIC_PLAN,
    RoutingPlanner,
    legal_routing_tools,
    resolve_default_planner,
)
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.vision import VisionVerdict
from private_trading_agents.workflow import DecisionSnapshot

OrchestratorMode = Literal["deterministic", "agentic"]


def run_agentic_orchestrator(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    bar_index: int | None = None,
    direction: str = "long",
    data_fresh: bool = True,
    market_actionable: bool = True,
    position_state: Literal["flat", "open"] = "flat",
    citations: list[CitationModel] | None = None,
    model: LoadedModel | None = None,
    model_id: UUID | None = None,
    model_mode: str | None = None,
    min_rr: str = "2.0",
    asset_class: str = "crypto",
    vision: VisionVerdict | None = None,
    planner: RoutingPlanner | None = None,
) -> DecisionSnapshot:
    """AG-01 tool loop: only routing tools, policy graph enforced.

    Planner may be fixed or LLM-backed; illegal proposals fall back to the fixed plan.
    """
    citation_models = [
        CitationModel.model_validate(
            item.model_dump() if hasattr(item, "model_dump") else item
        )
        for item in (citations or [])
    ]
    vision_in = None
    if vision is not None:
        vision_in = VisionAgentIn(
            attached=True,
            status=vision.status,
            consistent=vision.consistent,
            needs_clarification=vision.needs_clarification,
            blocker=vision.blocker,
        )
    OrchestratorAgentIn.model_validate(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": candles_to_models(bars),
            "bar_index": bar_index,
            "direction": direction,
            "data_fresh": data_fresh,
            "market_actionable": market_actionable,
            "position_state": position_state,
            "citations": citation_models,
            "min_rr": min_rr,
            "asset_class": asset_class,
            "model_id": model_id,
            "model_mode": model_mode,
            "model_present": model is not None,
            "vision": vision_in,
        }
    )

    state = OrchestratorState(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        bar_index=bar_index,
        direction=direction,
        data_fresh=data_fresh,
        market_actionable=market_actionable,
        position_state=position_state,
        citations=citation_models,
        min_rr=min_rr,
        asset_class=asset_class,
        model=model,
        model_id=model_id,
        model_mode=model_mode,
        vision_in=vision_in,
    )
    context = ToolContext(
        model=model,
        extras={"orchestrator_state": state},
    )
    active_planner = resolve_default_planner(explicit=planner)
    planner_kinds: list[str] = []
    max_steps = len(FIXED_AGENTIC_PLAN) + 4

    for _ in range(max_steps):
        if state.finished and state.snapshot is not None:
            break
        legal = legal_routing_tools(state.policy)
        if not legal:
            break
        tool = active_planner.choose_next(state, legal)
        kind = getattr(active_planner, "last_kind", active_planner.kind)
        planner_kinds.append(f"{tool.value}:{kind}")
        # Defense in depth — never invoke outside the legal set.
        if tool not in legal:
            from private_trading_agents.planner import fallback_from_fixed

            tool = fallback_from_fixed(legal)
            planner_kinds[-1] = f"{tool.value}:forced_fallback"
        call_tool(
            agent=AgentId.AG01_ORCHESTRATOR,
            tool=tool,
            payload={},
            context=context,
            note=f"plan:{tool.value}",
        )

    if state.snapshot is None:
        raise RuntimeError("agentic orchestrator finished without snapshot")

    evidence = dict(state.snapshot.evidence)
    evidence["planner"] = {
        "kind": active_planner.kind,
        "steps": planner_kinds,
    }
    state.snapshot.evidence = evidence
    return state.snapshot


def ag01_budget() -> AgentBudget:
    """Enough calls for the full routing plan (+ LLM retries headroom)."""
    return AgentBudget(max_tool_calls=len(FIXED_AGENTIC_PLAN) + 4, max_wall_ms=90_000.0)
