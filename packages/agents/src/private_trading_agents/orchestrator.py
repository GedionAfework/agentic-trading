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
from private_trading_agents.tools.context import ToolContext
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.vision import VisionVerdict
from private_trading_agents.workflow import DecisionSnapshot

# Policy-compliant planner order (no LLM yet — selects allowlisted routing tools).
_AGENTIC_PLAN: tuple[ToolId, ...] = (
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
) -> DecisionSnapshot:
    """AG-01 tool loop: only routing tools, policy graph enforced."""
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
    # AG-01 may call up to the full plan (+ small headroom).
    # Budget is applied via call_tool when session is active (set by workflow).
    for tool in _AGENTIC_PLAN:
        call_tool(
            agent=AgentId.AG01_ORCHESTRATOR,
            tool=tool,
            payload={},
            context=context,
            note=f"plan:{tool.value}",
        )
        if state.finished and state.snapshot is not None:
            return state.snapshot

    if state.snapshot is None:
        raise RuntimeError("agentic orchestrator finished without snapshot")
    return state.snapshot


def ag01_budget() -> AgentBudget:
    """Enough calls for the full routing plan."""
    return AgentBudget(max_tool_calls=len(_AGENTIC_PLAN) + 2, max_wall_ms=60_000.0)
