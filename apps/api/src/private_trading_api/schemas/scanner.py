from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)


class ScanRunOut(BaseModel):
    id: str | None = None
    instrument_symbol: str
    timeframe: str
    candle_open_time: str | None = None
    status: str
    action: str | None = None
    setup_state: str | None = None
    fresh: bool | None = None
    actionable: bool | None = None
    candidate_id: str | None = None
    candidate_new: bool | None = None
    error: str | None = None
    duration_ms: int | None = None


class ScanResponse(BaseModel):
    runs: list[ScanRunOut]


class SwitchesOut(BaseModel):
    scanner_enabled: bool
    notifications_enabled: bool


class SwitchUpdate(BaseModel):
    scanner_enabled: bool | None = None
    notifications_enabled: bool | None = None


class ScannerStatusOut(BaseModel):
    scanner_version: str
    switches: SwitchesOut
    timeframes: list[str]
    queues: dict[str, int | None]
    last_run: dict[str, Any]
    last_success: dict[str, str]
    dead_letters: int
    candidates_total: int
    candidates_published: int
    provider: dict[str, Any]


class CandidateOut(BaseModel):
    id: uuid.UUID
    dedupe_key: str
    strategy_code: str
    strategy_version_no: int
    instrument_symbol: str
    timeframe: str
    setup_anchor: str
    signal_type: str
    action: str
    candle_open_time: datetime
    decision_record_id: uuid.UUID | None
    publish_state: str
    seen_count: int
    payload: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
