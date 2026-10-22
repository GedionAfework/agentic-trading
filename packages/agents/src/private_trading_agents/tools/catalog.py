"""Registered tool catalog. Unregistered names cannot be invoked."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from private_trading_agents.tools.handlers import (
    handle_explain_grounded,
    handle_features_compute,
    handle_ml_rank,
    handle_risk_assess,
    handle_signal_check_gates,
    handle_strategy_evaluate,
    handle_vision_check_verdict,
)
from private_trading_agents.tools.ids import SideEffect, ToolId
from private_trading_agents.tools.schemas import (
    ExplainGroundedIn,
    ExplainGroundedOut,
    FeaturesComputeIn,
    FeaturesComputeOut,
    MlRankIn,
    MlRankOut,
    RiskAssessIn,
    RiskAssessOut,
    SignalCheckGatesIn,
    SignalCheckGatesOut,
    StrategyEvaluateIn,
    StrategyEvaluateOut,
    VisionCheckVerdictIn,
    VisionCheckVerdictOut,
)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: ToolId
    description: str
    side_effect: SideEffect
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., BaseModel]
    # If True, handler may accept opaque runtime context (e.g. LoadedModel).
    accepts_context: bool = False


TOOL_CATALOG: dict[ToolId, ToolSpec] = {
    ToolId.FEATURES_COMPUTE: ToolSpec(
        tool_id=ToolId.FEATURES_COMPUTE,
        description="Compute versioned feature facts from candle bars.",
        side_effect=SideEffect.NONE,
        input_model=FeaturesComputeIn,
        output_model=FeaturesComputeOut,
        handler=handle_features_compute,
    ),
    ToolId.STRATEGY_EVALUATE: ToolSpec(
        tool_id=ToolId.STRATEGY_EVALUATE,
        description="Evaluate versioned strategy rules and playbook levels.",
        side_effect=SideEffect.NONE,
        input_model=StrategyEvaluateIn,
        output_model=StrategyEvaluateOut,
        handler=handle_strategy_evaluate,
    ),
    ToolId.RISK_ASSESS: ToolSpec(
        tool_id=ToolId.RISK_ASSESS,
        description="Apply risk policy veto (R:R, freshness, actionability).",
        side_effect=SideEffect.NONE,
        input_model=RiskAssessIn,
        output_model=RiskAssessOut,
        handler=handle_risk_assess,
    ),
    ToolId.EXPLAIN_GROUNDED: ToolSpec(
        tool_id=ToolId.EXPLAIN_GROUNDED,
        description="Build a grounded explanation from structured facts only.",
        side_effect=SideEffect.NONE,
        input_model=ExplainGroundedIn,
        output_model=ExplainGroundedOut,
        handler=handle_explain_grounded,
    ),
    ToolId.SIGNAL_CHECK_GATES: ToolSpec(
        tool_id=ToolId.SIGNAL_CHECK_GATES,
        description="Bookkeep hard no-trade gates from setup/freshness state.",
        side_effect=SideEffect.NONE,
        input_model=SignalCheckGatesIn,
        output_model=SignalCheckGatesOut,
        handler=handle_signal_check_gates,
    ),
    ToolId.VISION_CHECK_VERDICT: ToolSpec(
        tool_id=ToolId.VISION_CHECK_VERDICT,
        description="Normalize vision supporting evidence; never authorizes trades.",
        side_effect=SideEffect.NONE,
        input_model=VisionCheckVerdictIn,
        output_model=VisionCheckVerdictOut,
        handler=handle_vision_check_verdict,
    ),
    ToolId.ML_RANK: ToolSpec(
        tool_id=ToolId.ML_RANK,
        description="Optional ML ranker; cannot open closed gates alone.",
        side_effect=SideEffect.NONE,
        input_model=MlRankIn,
        output_model=MlRankOut,
        handler=handle_ml_rank,
        accepts_context=True,
    ),
}


def get_tool(tool: ToolId | str) -> ToolSpec | None:
    try:
        tool_id = tool if isinstance(tool, ToolId) else ToolId(tool)
    except ValueError:
        return None
    return TOOL_CATALOG.get(tool_id)


def catalog_summary() -> list[dict[str, Any]]:
    return [
        {
            "tool": spec.tool_id.value,
            "description": spec.description,
            "side_effect": spec.side_effect.value,
            "accepts_context": spec.accepts_context,
        }
        for spec in TOOL_CATALOG.values()
    ]
