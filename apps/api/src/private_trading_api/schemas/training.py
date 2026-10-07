from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TrainingDatasetOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
    created_at: datetime


class TrainingVersionOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_no: int
    status: str
    fingerprint: str
    row_count: int
    object_key: str | None
    source_dataset_fingerprint: str
    label_policy: dict[str, Any]
    feature_schema: dict[str, Any]
    split_manifest: dict[str, Any]
    quality_report: dict[str, Any]
    engine_versions: dict[str, Any]
    created_at: datetime
    published_at: datetime | None


class BuildTrainingRequest(BaseModel):
    code: str = "frozen_bos_long_train_v1"
    name: str = "Frozen BOS long training set"
    backtest_dataset_id: uuid.UUID | None = None
    use_frozen_fixture: bool = True
    split_mode: Literal["time", "walk_forward"] = "time"


class BuildTrainingResponse(BaseModel):
    dataset: TrainingDatasetOut
    version: TrainingVersionOut
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
