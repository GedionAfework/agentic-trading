"""AG-07 Signal agent — hard no-trade gate bookkeeping."""

from __future__ import annotations

from private_trading_agents.agent_runtime import call_tool
from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    SignalAgentIn,
    SignalAgentOut,
)
from private_trading_agents.tools import ToolId
from private_trading_agents.tools.schemas import SignalCheckGatesOut


def run_signal_agent(payload: SignalAgentIn | dict) -> SignalAgentOut:
    inp = SignalAgentIn.model_validate(payload)
    result = call_tool(
        agent=AgentId.AG07_SIGNAL,
        tool=ToolId.SIGNAL_CHECK_GATES,
        payload={
            "setup_state": inp.setup_state,
            "data_fresh": inp.data_fresh,
            "market_actionable": inp.market_actionable,
            "hard_blockers": list(inp.hard_blockers),
        },
        note="check gates",
    )
    assert isinstance(result, SignalCheckGatesOut)
    return SignalAgentOut(
        gates_open_candidate=result.gates_open_candidate,
        hard_blockers=list(result.hard_blockers),
        step=AgentStep(
            agent=AgentId.AG07_SIGNAL,
            status="ok" if not result.hard_blockers else "blocked",
            note="hard no-trade gates",
        ),
    )
