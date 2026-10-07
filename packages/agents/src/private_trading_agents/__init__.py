"""Decision orchestrator — recommendation contract (Phase 12)."""

from private_trading_agents.workflow import (
    WORKFLOW_VERSION,
    CitationRef,
    DecisionAction,
    DecisionSnapshot,
    run_decision_workflow,
)

__all__ = [
    "WORKFLOW_VERSION",
    "CitationRef",
    "DecisionAction",
    "DecisionSnapshot",
    "run_decision_workflow",
]
__version__ = WORKFLOW_VERSION
