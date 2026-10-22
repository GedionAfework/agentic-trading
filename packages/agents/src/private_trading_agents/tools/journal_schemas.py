"""Pydantic I/O for AG-08 read-only journal tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JournalTradeRowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_code: str = Field(min_length=1, max_length=64)
    instrument_symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=12)
    session_bucket: str = Field(default="unknown", max_length=32)
    direction: str = Field(min_length=1, max_length=16)
    exit_reason: str | None = Field(default=None, max_length=64)
    realized_r: float | None = None
    realized_pnl: float | None = None
    won: bool | None = None


class JournalSummarizeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort: Literal["paper", "backtest", "manual"] = "paper"
    trades: list[JournalTradeRowModel] = Field(default_factory=list)
    strategy_code: str = "*"
    instrument_symbol: str = "*"
    timeframe: str = "*"
    session_bucket: str = "*"


class JournalSummarizeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort: str
    strategy_code: str
    instrument_symbol: str
    timeframe: str
    session_bucket: str
    sample_size: int
    sample_status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    # Cohorts must never be silently merged by this tool.
    merges_cohorts: Literal[False] = False


class JournalNarrateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: dict[str, Any]


class JournalNarrateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: str
    explanation_source: Literal["deterministic"] = "deterministic"
    authorizes_trade: Literal[False] = False
    kind: Literal["performance", "calibration"] = "performance"
