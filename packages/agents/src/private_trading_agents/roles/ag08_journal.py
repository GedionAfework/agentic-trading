"""AG-08 Journal agent — read-only cohort metrics + narration."""

from __future__ import annotations

from private_trading_agents.agent_runtime import call_tool
from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    JournalAgentIn,
    JournalAgentOut,
)
from private_trading_agents.tools import ToolId
from private_trading_agents.tools.journal_schemas import (
    JournalNarrateOut,
    JournalSummarizeOut,
)


def run_journal_agent(payload: JournalAgentIn | dict | None = None) -> JournalAgentOut:
    inp = JournalAgentIn.model_validate(payload or {})
    if not inp.enabled:
        return JournalAgentOut(
            enabled=False,
            step=AgentStep(
                agent=AgentId.AG08_JOURNAL,
                status="skipped",
                note="journal not enabled for this workflow",
            ),
        )

    if inp.snapshot is not None:
        snapshot = dict(inp.snapshot)
        if "cohort" not in snapshot:
            snapshot["cohort"] = inp.cohort
        sample_size = int(snapshot.get("sample_size") or 0)
        sample_status = str(snapshot.get("sample_status") or "unknown")
        metrics = dict(snapshot.get("metrics") or {})
        warnings = list(snapshot.get("warnings") or [])
    else:
        summarized = call_tool(
            agent=AgentId.AG08_JOURNAL,
            tool=ToolId.JOURNAL_SUMMARIZE_METRICS,
            payload={
                "cohort": inp.cohort,
                "trades": inp.trades,
                "strategy_code": inp.strategy_code,
                "instrument_symbol": inp.instrument_symbol,
                "timeframe": inp.timeframe,
                "session_bucket": inp.session_bucket,
            },
            note="summarize cohort metrics",
        )
        assert isinstance(summarized, JournalSummarizeOut)
        snapshot = {
            "cohort": summarized.cohort,
            "strategy_code": summarized.strategy_code,
            "instrument_symbol": summarized.instrument_symbol,
            "timeframe": summarized.timeframe,
            "session_bucket": summarized.session_bucket,
            "sample_size": summarized.sample_size,
            "sample_status": summarized.sample_status,
            "metrics": summarized.metrics,
            "warnings": summarized.warnings,
        }
        sample_size = summarized.sample_size
        sample_status = summarized.sample_status
        metrics = dict(summarized.metrics)
        warnings = list(summarized.warnings)

    narrated = call_tool(
        agent=AgentId.AG08_JOURNAL,
        tool=ToolId.JOURNAL_NARRATE_PERFORMANCE,
        payload={"snapshot": snapshot},
        note="narrate performance",
    )
    assert isinstance(narrated, JournalNarrateOut)

    return JournalAgentOut(
        enabled=True,
        cohort=str(snapshot.get("cohort")),
        sample_size=sample_size,
        sample_status=sample_status,
        metrics=metrics,
        warnings=warnings,
        narrative=narrated.narrative,
        authorizes_trade=False,
        step=AgentStep(
            agent=AgentId.AG08_JOURNAL,
            status="ok",
            note=f"cohort={snapshot.get('cohort')} n={sample_size}",
        ),
    )
