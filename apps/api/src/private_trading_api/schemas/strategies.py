from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StrategyOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
    created_at: datetime


class StrategyVersionOut(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    version_no: int
    status: str
    direction_mode: str
    engine_version: str
    published_at: datetime | None
    config: dict[str, Any]


class RuleOut(BaseModel):
    code: str
    name: str
    rule_type: str
    required: bool
    gate_group: str
    sort_order: int
    expression: dict[str, Any]


class EnsureStrategyResponse(BaseModel):
    strategy: StrategyOut
    version: StrategyVersionOut
    rules: list[RuleOut]


class EvaluateRequest(BaseModel):
    direction: str = Field(pattern="^(long|short)$")
    features: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class RuleEvalOut(BaseModel):
    code: str
    name: str
    result: str
    required: bool
    gate_group: str
    reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class AssessmentOut(BaseModel):
    strategy_code: str
    strategy_version_no: int
    engine_version: str
    direction: str
    setup_state: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    score: float | None
    rule_evaluations: list[RuleEvalOut]
    meta: dict[str, Any] = Field(default_factory=dict)


class TestCaseRunOut(BaseModel):
    code: str
    passed: bool
    expected_setup_state: str
    actual_setup_state: str
    expected_rule_results: dict[str, Any]
    actual_rule_results: dict[str, Any]
    blockers: list[str]
