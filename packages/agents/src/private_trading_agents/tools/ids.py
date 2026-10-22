"""Stable tool identifiers and side-effect classes."""

from __future__ import annotations

from enum import StrEnum


class ToolId(StrEnum):
    """Allowlisted tool names. Unknown IDs are never invokable."""

    FEATURES_COMPUTE = "features.compute"
    STRATEGY_EVALUATE = "strategy.evaluate"
    RISK_ASSESS = "risk.assess"
    EXPLAIN_GROUNDED = "explain.grounded"
    SIGNAL_CHECK_GATES = "signal.check_gates"
    VISION_CHECK_VERDICT = "vision.check_verdict"
    ML_RANK = "ml.rank"


class SideEffect(StrEnum):
    """Least-privilege side-effect class. Only NONE/READ are invokable today."""

    NONE = "none"  # pure compute, no I/O
    READ = "read"  # reads local state / computes from caller-supplied data
    WRITE = "write"  # mutates DB / files — denied unless explicitly enabled later
    EXTERNAL = "external"  # network / LLM — denied unless explicitly enabled later
    EXECUTE = "execute"  # orders / broker — never registered in baseline
