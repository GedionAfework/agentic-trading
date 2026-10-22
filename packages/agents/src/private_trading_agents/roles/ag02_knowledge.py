"""AG-02 Knowledge agent — grounded explanation from structured facts only."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    KnowledgeAgentIn,
    KnowledgeAgentOut,
)
from private_trading_agents.tools import ToolId, invoke_tool
from private_trading_agents.tools.schemas import ExplainGroundedOut


def run_knowledge_agent(payload: KnowledgeAgentIn | dict) -> KnowledgeAgentOut:
    inp = KnowledgeAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG02_KNOWLEDGE,
        tool=ToolId.EXPLAIN_GROUNDED,
        payload={"facts": inp.facts},
    )
    assert isinstance(result, ExplainGroundedOut)
    return KnowledgeAgentOut(
        explanation=result.explanation,
        explanation_source=result.explanation_source,
        step=AgentStep(
            agent=AgentId.AG02_KNOWLEDGE,
            status=AgentStatus.OK.value,
            note="grounded explanation",
        ),
    )
