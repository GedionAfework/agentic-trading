from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuleResult(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class SetupState(StrEnum):
    NO_SETUP = "no_setup"
    WATCH = "watch"
    WAIT_FOR_CONFIRMATION = "wait_for_confirmation"
    WAIT = "wait"
    READY_FOR_REVIEW = "ready_for_review"


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(slots=True, frozen=True)
class FeatureFact:
    """Normalized feature fact for rule evaluation (no look-ahead here — caller supplies)."""

    status: RuleResult
    value: Any = None
    reason: str | None = None


@dataclass(slots=True)
class RuleEvaluation:
    code: str
    name: str
    result: RuleResult
    required: bool
    gate_group: str
    reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyAssessment:
    strategy_code: str
    strategy_version_no: int
    engine_version: str
    direction: Direction
    setup_state: SetupState
    rule_evaluations: list[RuleEvaluation]
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.setup_state == SetupState.READY_FOR_REVIEW
