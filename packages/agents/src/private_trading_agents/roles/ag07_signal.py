"""AG-07 Signal agent — hard no-trade gate bookkeeping."""

from __future__ import annotations

from private_trading_strategies.types import SetupState

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    SignalAgentIn,
    SignalAgentOut,
)


def run_signal_agent(payload: SignalAgentIn | dict) -> SignalAgentOut:
    inp = SignalAgentIn.model_validate(payload)
    blockers = list(inp.hard_blockers)
    if not inp.data_fresh and "stale_market_data" not in blockers:
        blockers.append("stale_market_data")
    if not inp.market_actionable and "market_not_actionable" not in blockers:
        blockers.append("market_not_actionable")
    ready = inp.setup_state == SetupState.READY_FOR_REVIEW.value
    # Risk approval is applied by AG-06 / orchestrator after this step.
    gates_open_candidate = inp.data_fresh and inp.market_actionable and ready
    return SignalAgentOut(
        gates_open_candidate=gates_open_candidate,
        hard_blockers=blockers,
        step=AgentStep(
            agent=AgentId.AG07_SIGNAL,
            status="ok" if not blockers else "blocked",
            note="hard no-trade gates",
        ),
    )
