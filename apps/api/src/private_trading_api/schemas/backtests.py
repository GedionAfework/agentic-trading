from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetOut(BaseModel):
    id: uuid.UUID
    code: str
    symbol: str
    timeframe: str
    source: str
    fingerprint: str
    bar_count: int
    created_at: datetime


class RunBacktestRequest(BaseModel):
    dataset_id: uuid.UUID | None = None
    use_frozen_fixture: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    status: str
    strategy_code: str
    strategy_version_no: int
    risk_policy_code: str
    risk_policy_version_no: int
    engine_version: str
    feature_engine_version: str
    strategy_engine_version: str
    risk_engine_version: str
    dataset_fingerprint: str
    report: dict[str, Any]
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
