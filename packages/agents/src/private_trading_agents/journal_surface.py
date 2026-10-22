"""Journal product surface — AG-08 read-only narration; never trade authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from private_trading_core.errors import ForbiddenError

from private_trading_agents.agent_runtime import agent_session
from private_trading_agents.contracts import AgentId
from private_trading_agents.roles.ag08_journal import run_journal_agent
from private_trading_agents.tools.ids import ToolId
from private_trading_agents.tools.injection import (
    assert_tool_policy_intact,
    policy_fingerprint,
)
from private_trading_agents.tools.permissions import has_permission

_JOURNAL_BANNED_TOOLS = frozenset(
    {
        ToolId.WORKFLOW_FINISH,
        ToolId.RISK_ASSESS,
        ToolId.STRATEGY_EVALUATE,
        ToolId.FEATURES_COMPUTE,
        ToolId.SIGNAL_CHECK_GATES,
        ToolId.ML_RANK,
        ToolId.KNOWLEDGE_ASK,
        ToolId.AGENT_RUN_RISK,
        ToolId.AGENT_RUN_STRATEGY,
    }
)


class JournalTradeAuthorityError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "Journal agent has no trade authority",
            details={"agent": AgentId.AG08_JOURNAL.value, "authorizes_trade": False},
        )
        self.code = "JOURNAL_NO_TRADE_AUTHORITY"


@dataclass(slots=True)
class JournalNarrateResult:
    narrative: str
    cohort: str
    sample_size: int | None
    sample_status: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    agent: str = AgentId.AG08_JOURNAL.value
    tool: str = ToolId.JOURNAL_NARRATE_PERFORMANCE.value
    authorizes_trade: Literal[False] = False
    decision_action: None = None
    tool_traces: list[dict[str, Any]] = field(default_factory=list)
    policy_fingerprint: str = ""

    def meta(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "tool": self.tool,
            "authorizes_trade": False,
            "decision_action": None,
            "tool_traces": list(self.tool_traces),
            "policy_fingerprint": self.policy_fingerprint,
            "sample_size": self.sample_size,
            "sample_status": self.sample_status,
            "surface": "journal_ai",
        }


def assert_journal_surface_permissions() -> None:
    if not has_permission(AgentId.AG08_JOURNAL, ToolId.JOURNAL_NARRATE_PERFORMANCE):
        raise ForbiddenError(
            "AG-08 is not permitted to invoke journal.narrate_performance",
            details={"agent": "AG-08", "tool": "journal.narrate_performance"},
        )
    if not has_permission(AgentId.AG08_JOURNAL, ToolId.JOURNAL_SUMMARIZE_METRICS):
        raise ForbiddenError(
            "AG-08 is not permitted to invoke journal.summarize_metrics",
            details={"agent": "AG-08", "tool": "journal.summarize_metrics"},
        )
    if not has_permission(AgentId.AG08_JOURNAL, ToolId.JOURNAL_NARRATE_CALIBRATION):
        raise ForbiddenError(
            "AG-08 is not permitted to invoke journal.narrate_calibration",
            details={"agent": "AG-08", "tool": "journal.narrate_calibration"},
        )
    for tool in _JOURNAL_BANNED_TOOLS:
        if has_permission(AgentId.AG08_JOURNAL, tool):
            raise JournalTradeAuthorityError()


def run_journal_narrate_surface(*, snapshot: dict[str, Any]) -> JournalNarrateResult:
    """Narrate a cohort performance snapshot through AG-08 tools only."""
    assert_journal_surface_permissions()
    assert_tool_policy_intact()
    sealed = policy_fingerprint()
    cohort = str(snapshot.get("cohort") or "paper")

    with agent_session() as session:
        out = run_journal_agent(
            {
                "enabled": True,
                "cohort": cohort,
                "snapshot": snapshot,
            }
        )
        traces = session.as_dicts()

    assert_tool_policy_intact()
    if policy_fingerprint() != sealed:
        raise JournalTradeAuthorityError()
    assert_journal_surface_permissions()
    if out.authorizes_trade:
        raise JournalTradeAuthorityError()
    if not out.narrative:
        raise ForbiddenError("Journal narration produced no text", retryable=False)

    return JournalNarrateResult(
        narrative=out.narrative,
        cohort=cohort,
        sample_size=out.sample_size,
        sample_status=out.sample_status,
        metrics=dict(out.metrics),
        warnings=list(out.warnings),
        tool=ToolId.JOURNAL_NARRATE_PERFORMANCE.value,
        tool_traces=traces,
        policy_fingerprint=sealed,
    )


def run_journal_calibration_surface(*, snapshot: dict[str, Any]) -> JournalNarrateResult:
    """Narrate calibration via AG-08; never authorizes retrain or trades."""
    from private_trading_agents.agent_runtime import call_tool
    from private_trading_agents.tools.journal_schemas import JournalNarrateOut

    assert_journal_surface_permissions()
    assert_tool_policy_intact()
    sealed = policy_fingerprint()
    cohort = str(snapshot.get("cohort") or "paper")

    with agent_session() as session:
        narrated = call_tool(
            agent=AgentId.AG08_JOURNAL,
            tool=ToolId.JOURNAL_NARRATE_CALIBRATION,
            payload={"snapshot": snapshot},
            note="journal_calibration_surface",
        )
        assert isinstance(narrated, JournalNarrateOut)
        traces = session.as_dicts()

    assert_tool_policy_intact()
    if policy_fingerprint() != sealed:
        raise JournalTradeAuthorityError()
    assert_journal_surface_permissions()

    return JournalNarrateResult(
        narrative=narrated.narrative,
        cohort=cohort,
        sample_size=int(snapshot.get("sample_size") or 0),
        sample_status=str(snapshot.get("sample_status") or "unknown"),
        metrics={},
        warnings=list(snapshot.get("warnings") or []),
        tool=ToolId.JOURNAL_NARRATE_CALIBRATION.value,
        tool_traces=traces,
        policy_fingerprint=sealed,
    )
