from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CitationIn(BaseModel):
    citation_id: str
    excerpt: str = ""
    document_id: str | None = None


class RunDecisionRequest(BaseModel):
    use_frozen_fixture: bool = True
    bar_index: int | None = None
    data_fresh: bool = True
    market_actionable: bool = True
    position_state: Literal["flat", "open"] = "flat"
    citations: list[CitationIn] = Field(default_factory=list)
    decision_model_id: uuid.UUID | None = None
    screenshot_job_id: uuid.UUID | None = None


class DecisionRecordOut(BaseModel):
    id: uuid.UUID
    symbol: str
    timeframe: str
    bar_open_time: datetime
    action: str
    direction: str
    setup_state: str
    confidence_band: str
    strategy_code: str
    strategy_version_no: int
    risk_approved: bool
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    rr_ratio: float | None
    model_id: uuid.UUID | None
    model_score: float | None
    model_band: str | None
    explanation: str
    explanation_source: str
    evidence: dict[str, Any]
    workflow: list[dict[str, Any]]
    hard_blockers: list[str]
    created_at: datetime
