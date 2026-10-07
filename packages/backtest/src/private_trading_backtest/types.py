from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class OutcomeSource(StrEnum):
    """BR-008: never silently merge cohorts."""

    BACKTEST = "backtest"
    PAPER = "paper"
    MANUAL = "manual"


class FillPolicy(StrEnum):
    NEXT_OPEN = "next_open"  # signal on bar i → fill at i+1 open


@dataclass(slots=True, frozen=True)
class CostModel:
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    spread_bps: Decimal = Decimal("2")

    @property
    def round_trip_bps(self) -> Decimal:
        # fee both sides + slippage both sides + half-spread approx both sides
        return (self.fee_bps + self.slippage_bps) * 2 + self.spread_bps


@dataclass(slots=True)
class SimulatedTrade:
    trade_id: int
    direction: str
    signal_bar_index: int
    entry_bar_index: int
    exit_bar_index: int
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    qty: Decimal
    pnl: Decimal
    pnl_r: Decimal
    exit_reason: str
    costs: Decimal
    outcome_source: str = OutcomeSource.BACKTEST.value


@dataclass(slots=True)
class BacktestMetrics:
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float | None
    expectancy_r: float | None
    total_pnl: Decimal
    max_drawdown_pnl: Decimal
    slices: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestReport:
    metrics: BacktestMetrics
    trades: list[SimulatedTrade]
    pins: dict[str, Any]
    config: dict[str, Any]
    bar_count: int
    signals_seen: int
    notes: list[str] = field(default_factory=list)
