from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AcceptPaperTradeRequest(BaseModel):
    decision_record_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None


class PaperAccountOut(BaseModel):
    account_id: uuid.UUID
    label: str
    currency: str
    starting_equity: str
    equity: str
    fill_model: dict[str, Any]
    trades_by_status: dict[str, int]
    closed_trades: int
    sum_realized_r: str
    soak: dict[str, Any]
    integrity: dict[str, Any]


class PaperTradeOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    decision_record_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    instrument_symbol: str
    timeframe: str
    direction: str
    status: str
    label: str
    signal_bar_open_time: datetime
    planned_entry: float
    stop_price: float
    target_price: float
    invalidation_price: float | None
    qty: float
    risk_amount: float
    fill_model: dict[str, Any]
    entry_price: float | None
    entry_bar_open_time: datetime | None
    exit_price: float | None
    exit_bar_open_time: datetime | None
    exit_reason: str | None
    realized_pnl: float | None
    realized_r: float | None
    costs: float
    bars_held: int
    journal_entry_id: uuid.UUID | None
    notes: list[Any]
    created_at: datetime
    closed_at: datetime | None


class PaperEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    bar_open_time: datetime | None
    payload: dict[str, Any]
    created_at: datetime


class PaperTradeDetailOut(PaperTradeOut):
    events: list[PaperEventOut] = Field(default_factory=list)


class MonitorOut(BaseModel):
    processed: int
    ready: int
    open: int
    closed: int
    unchanged: int


class JournalEntryOut(BaseModel):
    id: uuid.UUID
    cohort: str
    instrument_symbol: str
    timeframe: str
    direction: str
    outcome: str
    realized_r: float | None
    realized_pnl: float | None
    summary: str
    details: dict[str, Any]
    paper_trade_id: uuid.UUID | None
    created_at: datetime
