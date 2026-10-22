"""AG-09 Decision ML agent — optional ranker; never overrides closed gates alone."""

from __future__ import annotations

from typing import Any

from private_trading_agents.adapters import feature_models_to_payload
from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    DecisionMlAgentIn,
    DecisionMlAgentOut,
)


def run_decision_ml_agent(
    payload: DecisionMlAgentIn | dict,
    *,
    model: Any | None = None,
) -> DecisionMlAgentOut:
    inp = DecisionMlAgentIn.model_validate(payload)
    if model is None or not inp.model_present or not inp.gates_open:
        return DecisionMlAgentOut(
            invoked=False,
            step=AgentStep(
                agent=AgentId.AG09_DECISION_ML,
                status="skipped",
                note="ranker omitted or gates already closed",
            ),
        )
    features = feature_models_to_payload(inp.features)
    ranked = model.decide(
        features,
        strategy_ready=True,
        risk_approved=True,
        mode=inp.model_mode or "shadow",
    )
    return DecisionMlAgentOut(
        invoked=True,
        model_score=ranked.score,
        model_band=ranked.band,
        recommends_enter=ranked.recommendation == "ENTER",
        step=AgentStep(
            agent=AgentId.AG09_DECISION_ML,
            status="scored",
            note=f"band={ranked.band} mode={inp.model_mode or 'shadow'}",
        ),
    )
