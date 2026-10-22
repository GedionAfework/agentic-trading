"""AG-08 Journal agent — stub contract (narrative later)."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    JournalAgentIn,
    JournalAgentOut,
)


def run_journal_agent(payload: JournalAgentIn | dict | None = None) -> JournalAgentOut:
    JournalAgentIn.model_validate(payload or {})
    return JournalAgentOut(
        step=AgentStep(
            agent=AgentId.AG08_JOURNAL,
            status="skipped",
            note="journal is a later phase",
        )
    )
