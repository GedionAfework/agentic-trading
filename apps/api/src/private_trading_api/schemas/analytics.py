from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PerformanceSnapshotOut(BaseModel):
    id: uuid.UUID
    cohort: str
    grain: str
    strategy_code: str
    instrument_symbol: str
    timeframe: str
    session_bucket: str
    sample_size: int
    sample_status: str
    metrics: dict[str, Any]
    warnings: list[Any]
    computed_at: datetime


class CalibrationSnapshotOut(BaseModel):
    id: uuid.UUID
    cohort: str
    band_field: str
    sample_size: int
    sample_status: str
    bands: dict[str, Any]
    drift_flags: list[Any]
    warnings: list[Any]
    computed_at: datetime


class RefreshRequest(BaseModel):
    cohort: str = Field(default="paper", pattern="^(paper|backtest)$")


class NarrateOut(BaseModel):
    snapshot_id: uuid.UUID
    cohort: str
    narrative: str


class FeedbackCreate(BaseModel):
    action: str
    note: str | None = None
    candidate_id: uuid.UUID | None = None
    decision_record_id: uuid.UUID | None = None


class FeedbackResolve(BaseModel):
    status: str = Field(default="resolved", pattern="^(resolved|dismissed)$")
    resolution_note: str | None = None


class FeedbackOut(BaseModel):
    id: uuid.UUID
    source: str
    source_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    decision_record_id: uuid.UUID | None
    action: str
    status: str
    note: str | None
    payload: dict[str, Any]
    resolution_note: str | None
    resolved_at: datetime | None
    created_at: datetime


class RetrainCreate(BaseModel):
    decision_model_code: str
    reason: str
    reason_codes: list[str] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)


class RetrainApprove(BaseModel):
    reason_codes: list[str] | None = None
    evaluation: dict[str, Any] | None = None


class RetrainReject(BaseModel):
    rejection_reason: str


class RetrainOut(BaseModel):
    id: uuid.UUID
    decision_model_code: str
    reason: str
    reason_codes: list[Any]
    evaluation: dict[str, Any]
    status: str
    rejection_reason: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    executed_at: datetime | None
    resulting_model_ids: list[Any]
    created_at: datetime
    policy: str
