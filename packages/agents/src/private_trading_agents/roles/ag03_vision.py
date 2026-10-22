"""AG-03 Vision agent — supporting evidence only; never authorizes trades."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    VisionAgentIn,
    VisionAgentOut,
)


def run_vision_agent(payload: VisionAgentIn | dict | None) -> VisionAgentOut:
    if payload is None:
        inp = VisionAgentIn(attached=False)
    else:
        inp = VisionAgentIn.model_validate(payload)
    if not inp.attached:
        return VisionAgentOut(
            needs_clarification=False,
            blocker=None,
            step=AgentStep(
                agent=AgentId.AG03_VISION,
                status="skipped",
                note="vision not attached",
            ),
        )
    return VisionAgentOut(
        needs_clarification=inp.needs_clarification,
        blocker=inp.blocker,
        step=AgentStep(
            agent=AgentId.AG03_VISION,
            status=inp.status or "ok",
            note="supporting evidence only",
        ),
    )
