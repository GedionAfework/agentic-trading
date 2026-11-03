"""Pydantic I/O for the AG-06 read-only portfolio status tool."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PortfolioExposureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    asset_class: Literal["crypto", "forex"] = "crypto"
    direction: Literal["long", "short"] = "long"
    risk_pct: Decimal = Field(gt=0, le=Decimal("5"))


class PortfolioStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_exposures: list[PortfolioExposureIn] = Field(default_factory=list, max_length=50)
    daily_realized_pnl_pct: Decimal = Decimal("0")
    # symbol -> risk % a paper open would use
    candidates: dict[str, Decimal] = Field(default_factory=dict, max_length=20)


class PortfolioSymbolVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    proposed_risk_pct: str
    portfolio_allows_open: bool
    blockers: list[str] = Field(default_factory=list)


class PortfolioStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_open_risk_pct: str
    total_headroom_pct: str
    crypto_open_risk_pct: str
    crypto_headroom_pct: str
    daily_loss_stop_hit: bool
    symbols: list[PortfolioSymbolVerdict] = Field(default_factory=list)
    explanation: str
    explanation_source: Literal["deterministic"] = "deterministic"
    # Read-only view: a free cap is never a trade instruction.
    authorizes_trade: Literal[False] = False
