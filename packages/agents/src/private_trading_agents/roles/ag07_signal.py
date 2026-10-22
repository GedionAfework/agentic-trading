"""AG-07 Signal agent — hard no-trade gate bookkeeping."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    SignalAgentIn,
    SignalAgentOut,
)
from private_trading_agents.tools import ToolId, invoke_tool
from private_trading_agents.tools.schemas import SignalCheckGatesOut


def run_signal_agent(payload: SignalAgentIn | dict) -> SignalAgentOut:
    inp = SignalAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG07_SIGNAL,
        tool=ToolId.SIGNAL_CHECK_GATES,
        payload={
            "setup_state": inp.setup_state,
            "data_fresh": inp.data_fresh,
            "market_actionable": inp.market_actionable,
            "hard_blockers": list(inp.hard_blockers),
        },
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
