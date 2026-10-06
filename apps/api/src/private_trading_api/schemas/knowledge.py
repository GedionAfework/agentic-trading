from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    document_type: str
    authority_tier: int
    status: str
    current_version_id: uuid.UUID | None
    asset_class: str | None
    strategy_tag: str | None
    timeframe_tag: str | None
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    strategy_tag: str | None = None
    asset_class: str | None = None
    timeframe_tag: str | None = None


class CitationOut(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    page: int | None = None
    title: str
    authority_tier: int
    score: float | None = None


class AskResponse(BaseModel):
    answer: str
    sufficient_evidence: bool
    confidence: str
    citations: list[CitationOut]
    retrieval_event_id: uuid.UUID
    conflicts: list[str] = Field(default_factory=list)
    model: str
    prompt_version: str
    meta: dict[str, Any] = Field(default_factory=dict)
