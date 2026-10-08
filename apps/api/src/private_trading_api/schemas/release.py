from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReleasePolicyOut(BaseModel):
    live_alerts_enabled: bool
    approved_symbols: list[str]
    approved_timeframes: list[str]
    channels: list[str]
    quiet_hours_utc_start: int | None
    quiet_hours_utc_end: int | None
    require_checklist: bool
    require_soak: bool
    require_integrity: bool
    min_confidence_band: str
    allow_actions: list[str]
    notes: str


class ReleasePolicyUpdate(BaseModel):
    approved_symbols: list[str] | None = None
    approved_timeframes: list[str] | None = None
    channels: list[str] | None = None
    quiet_hours_utc_start: int | None = None
    quiet_hours_utc_end: int | None = None
    require_checklist: bool | None = None
    require_soak: bool | None = None
    require_integrity: bool | None = None
    min_confidence_band: str | None = None
    allow_actions: list[str] | None = None
    notes: str | None = None


class SignGateRequest(BaseModel):
    gate: str = Field(min_length=1, max_length=8)
    notes: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class WaiverCreate(BaseModel):
    code: str
    requirement: str
    reason: str
    expires_at: datetime | None = None


class LiveAlertsToggle(BaseModel):
    enabled: bool
    force: bool = False
