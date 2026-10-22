"""AG-09 Decision ML agent — optional ranker; never overrides closed gates alone."""

from __future__ import annotations

from typing import Any

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    DecisionMlAgentIn,
    DecisionMlAgentOut,
)
from private_trading_agents.tools import ToolContext, ToolId, invoke_tool
from private_trading_agents.tools.schemas import MlRankOut


def run_decision_ml_agent(
    payload: DecisionMlAgentIn | dict,
    *,
    model: Any | None = None,
) -> DecisionMlAgentOut:
    inp = DecisionMlAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG09_DECISION_ML,
        tool=ToolId.ML_RANK,
        payload={
            "features": {
                name: fact.model_dump() for name, fact in inp.features.items()
            },
            "gates_open": inp.gates_open,
            "model_mode": inp.model_mode,
            "model_present": inp.model_present,
        },
        context=ToolContext(model=model),
    )
    assert isinstance(result, MlRankOut)
    return DecisionMlAgentOut(
        invoked=result.invoked,
        model_score=result.model_score,
        model_band=result.model_band,
        recommends_enter=result.recommends_enter,
        step=AgentStep(
            agent=AgentId.AG09_DECISION_ML,
            status=result.status,
            note=result.note,
        ),
    )
