"""AG-03 Vision agent — supporting evidence only; never authorizes trades."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    VisionAgentIn,
    VisionAgentOut,
)
from private_trading_agents.tools import ToolId, invoke_tool
from private_trading_agents.tools.schemas import VisionCheckVerdictOut


def run_vision_agent(payload: VisionAgentIn | dict | None) -> VisionAgentOut:
    if payload is None:
        inp = VisionAgentIn(attached=False)
    else:
        inp = VisionAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG03_VISION,
        tool=ToolId.VISION_CHECK_VERDICT,
        payload={
            "attached": inp.attached,
            "status": inp.status,
            "consistent": inp.consistent,
            "needs_clarification": inp.needs_clarification,
            "blocker": inp.blocker,
        },
    )
    assert isinstance(result, VisionCheckVerdictOut)
    return VisionAgentOut(
        needs_clarification=result.needs_clarification,
        blocker=result.blocker,
        step=AgentStep(
            agent=AgentId.AG03_VISION,
            status=result.status,
            note=(
                "vision not attached"
                if result.skipped
                else "supporting evidence only"
            ),
        ),
    )
