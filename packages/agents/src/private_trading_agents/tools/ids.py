"""Stable tool identifiers and side-effect classes."""

from __future__ import annotations

from enum import StrEnum


class ToolId(StrEnum):
    """Allowlisted tool names. Unknown IDs are never invokable."""

    # Specialist compute tools (never granted to AG-01)
    FEATURES_COMPUTE = "features.compute"
    STRATEGY_EVALUATE = "strategy.evaluate"
    RISK_ASSESS = "risk.assess"
    EXPLAIN_GROUNDED = "explain.grounded"
    SIGNAL_CHECK_GATES = "signal.check_gates"
    VISION_CHECK_VERDICT = "vision.check_verdict"
    ML_RANK = "ml.rank"

    # EXTERNAL tools — require agent_external_tools_enabled (or context override)
    KNOWLEDGE_RETRIEVE = "knowledge.retrieve"
    KNOWLEDGE_ASK = "knowledge.ask"
    VISION_EXTRACT = "vision.extract"
    LLM_NARRATE_FACTS = "llm.narrate_facts"

    # AG-01 routing tools only — call specialists, never raw engines
    AGENT_RUN_MARKET_DATA = "agent.run_market_data"
    AGENT_RUN_VISION = "agent.run_vision"
    AGENT_RUN_JOURNAL = "agent.run_journal"
    AGENT_RUN_STRATEGY = "agent.run_strategy"
    AGENT_RUN_SIGNAL = "agent.run_signal"
    AGENT_RUN_RISK = "agent.run_risk"
    AGENT_RUN_ML = "agent.run_ml"
    AGENT_RUN_KNOWLEDGE = "agent.run_knowledge"
    WORKFLOW_FINISH = "workflow.finish"


class SideEffect(StrEnum):
    """Least-privilege side-effect class. Only NONE/READ are invokable today."""

    NONE = "none"  # pure compute, no I/O
    READ = "read"  # reads local state / computes from caller-supplied data
    WRITE = "write"  # mutates DB / files — denied unless explicitly enabled later
    EXTERNAL = "external"  # network / LLM — denied unless explicitly enabled later
    EXECUTE = "execute"  # orders / broker — never registered in baseline
