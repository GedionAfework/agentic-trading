from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RiskPolicyOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
    created_at: datetime


class RiskPolicyVersionOut(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    version_no: int
    status: str
    engine_version: str
    published_at: datetime | None
    config: dict[str, Any]


class EnsureRiskPolicyResponse(BaseModel):
    policy: RiskPolicyOut
    version: RiskPolicyVersionOut


class InstrumentMetaIn(BaseModel):
    asset_class: str = "crypto"
    price_tick: Decimal | None = None
    qty_step: Decimal | None = None
    min_notional: Decimal | None = None
    pip_size: Decimal | None = None
    lot_size: Decimal | None = None


class AssessRiskRequest(BaseModel):
    direction: str = Field(pattern="^(long|short)$")
    entry: Decimal | None = None
    stop: Decimal | None = None
    target_1: Decimal | None = None
    data_fresh: bool = True
    market_actionable: bool = True
    is_weekend: bool = False
    in_event_blackout: bool = False
    account_equity: Decimal | None = None
    open_risk_pct: Decimal | None = None
    summary_text: str | None = None
    instrument: InstrumentMetaIn | None = None
    setup_id: uuid.UUID | None = None


class PaperSizeOut(BaseModel):
    risk_pct: str | None = None
    risk_amount: str | None = None
    quantity: str | None = None
    notional: str | None = None
    notes: list[str] = Field(default_factory=list)


class RiskAssessmentOut(BaseModel):
    id: uuid.UUID
    approved: bool
    direction: str
    entry_reference: Decimal | None
    stop_price: Decimal | None
    target_1: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    rr_ratio: Decimal | None
    hard_blockers: list[str]
    warnings: list[str]
    paper_size: PaperSizeOut
    engine_version: str
    policy_code: str
    policy_version_no: int
    meta: dict[str, Any] = Field(default_factory=dict)
