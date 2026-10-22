"""AG-02 Knowledge agent — grounded explanation from structured facts only."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    KnowledgeAgentIn,
    KnowledgeAgentOut,
)
from private_trading_agents.explain import grounded_explanation


def run_knowledge_agent(payload: KnowledgeAgentIn | dict) -> KnowledgeAgentOut:
    inp = KnowledgeAgentIn.model_validate(payload)
    # Citations are structured IDs/excerpts already in facts when provided by orchestrator.
    explanation = grounded_explanation(inp.facts)
    return KnowledgeAgentOut(
        explanation=explanation,
        explanation_source="deterministic",
        step=AgentStep(
            agent=AgentId.AG02_KNOWLEDGE,
            status=AgentStatus.OK.value,
            note="grounded explanation",
        ),
    )
