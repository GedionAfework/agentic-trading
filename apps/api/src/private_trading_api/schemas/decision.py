from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionModelOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    algorithm: str
    role: str
    mode: str
    status: str
    fingerprint: str
    training_dataset_version_id: uuid.UUID | None
    training_window: dict[str, Any]
    metrics: dict[str, Any]
    feature_importance: list[dict[str, Any]]
    hyperparameters: dict[str, Any]
    engine_version: str
    created_at: datetime
    promoted_at: datetime | None


class TrainDecisionRequest(BaseModel):
    training_version_id: uuid.UUID
    code: str = "decision-lgbm-v1"
    name: str = "Decision ranker v1"


class TrainDecisionResponse(BaseModel):
    baseline: DecisionModelOut
    challenger: DecisionModelOut
    recommended_role: str
    notes: list[str] = Field(
        default_factory=lambda: [
            "Models are registered in shadow mode.",
            "Out-of-sample metrics are on the test split and were not used for tuning.",
        ]
    )


class PredictDecisionRequest(BaseModel):
    features: dict[str, Any]
    strategy_ready: bool
    risk_approved: bool
    hard_blockers: list[str] = Field(default_factory=list)


class PredictDecisionResponse(BaseModel):
    model_id: uuid.UUID
    mode: str
    recommendation: str
    reason: str
    score: float | None
    band: str
    abstained: bool
    gates_passed: bool
    hard_blockers: list[str]
    score_kind: str
    not_a_calibrated_probability: bool
    llm_may_invent_probability: bool
    cannot_bypass_strategy_or_risk: bool
