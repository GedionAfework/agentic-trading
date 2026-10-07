from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


class WeekendPolicy(StrEnum):
    HARD_BLOCK = "hard_block"
    WARN = "warn"
    IGNORE = "ignore"


@dataclass(slots=True, frozen=True)
class InstrumentRiskMeta:
    asset_class: str
    price_tick: Decimal | None = None
    qty_step: Decimal | None = None
    min_notional: Decimal | None = None
    # FX scaffolding
    pip_size: Decimal | None = None
    lot_size: Decimal | None = None


@dataclass(slots=True, frozen=True)
class RiskInput:
    direction: Direction
    entry: Decimal | None
    stop: Decimal | None
    target_1: Decimal | None
    data_fresh: bool = True
    market_actionable: bool = True
    is_weekend: bool = False
    in_event_blackout: bool = False
    account_equity: Decimal | None = None
    open_risk_pct: Decimal | None = None
    summary_text: str | None = None
    instrument: InstrumentRiskMeta | None = None
    setup_id: str | None = None


@dataclass(slots=True)
class PaperSizeSuggestion:
    risk_pct: Decimal
    risk_amount: Decimal | None
    quantity: Decimal | None
    notional: Decimal | None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RiskAssessmentResult:
    approved: bool
    direction: Direction
    entry_reference: Decimal | None
    stop_price: Decimal | None
    target_1: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    rr_ratio: Decimal | None
    hard_blockers: list[str]
    warnings: list[str]
    paper_size: PaperSizeSuggestion | None
    engine_version: str
    policy_code: str
    policy_version_no: int
    meta: dict[str, Any] = field(default_factory=dict)
