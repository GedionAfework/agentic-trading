from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScreenshotJobOut(BaseModel):
    id: uuid.UUID
    status: str
    content_type: str
    byte_size: int
    market_symbol: str | None
    market_timeframe: str | None
    extraction: dict[str, Any]
    verification: dict[str, Any]
    authorizes_trade: bool
    corrected_symbol: str | None
    corrected_timeframe: str | None
    retain_until: datetime
    created_at: datetime


class CorrectScreenshotRequest(BaseModel):
    symbol: str
    timeframe: str


class GateDReport(BaseModel):
    gate: str
    engine_version: str
    case_count: int
    fabricated_price_count: int
    authorizes_trade_count: int
    consistent_accuracy: float
    clarification_rate: float
    passed: bool
    mode: str
    note: str = Field(default="")
