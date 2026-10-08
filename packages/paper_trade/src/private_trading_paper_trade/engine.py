"""Pure paper lifecycle: ready → open → closed. Conservative same-candle; no look-ahead."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from private_trading_features.types import CandleBar

from private_trading_paper_trade.fill_model import (
    PAPER_LABEL,
    entry_fill,
    exit_fill,
    max_bars,
    round_trip_costs,
)

STATUS_READY = "ready"
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_CANCELLED = "cancelled"


@dataclass(slots=True)
class PaperPlan:
    symbol: str
    timeframe: str
    direction: str
    signal_bar_open_time: datetime
    planned_entry: Decimal
    stop_price: Decimal
    target_price: Decimal
    invalidation_price: Decimal | None
    qty: Decimal
    risk_amount: Decimal
    fill_model: dict[str, Any]
    decision_record_id: str | None = None
    candidate_id: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FillOutcome:
    filled: bool
    entry_price: Decimal | None = None
    entry_bar_open_time: datetime | None = None
    note: str | None = None


@dataclass(slots=True)
class ExitOutcome:
    closed: bool
    exit_price: Decimal | None = None
    exit_reason: str | None = None
    exit_bar_open_time: datetime | None = None
    realized_pnl: Decimal | None = None
    realized_r: Decimal | None = None
    costs: Decimal = Decimal("0")
    bars_held: int = 0
    note: str | None = None


def validate_plan(plan: PaperPlan) -> list[str]:
    blockers: list[str] = []
    if plan.direction not in {"long", "short"}:
        blockers.append("invalid_direction")
    if plan.qty <= 0:
        blockers.append("non_positive_qty")
    if plan.risk_amount <= 0:
        blockers.append("non_positive_risk")
    if plan.direction == "long":
        if plan.stop_price >= plan.planned_entry:
            blockers.append("long_stop_not_below_entry")
        if plan.target_price <= plan.planned_entry:
            blockers.append("long_target_not_above_entry")
    else:
        if plan.stop_price <= plan.planned_entry:
            blockers.append("short_stop_not_above_entry")
        if plan.target_price >= plan.planned_entry:
            blockers.append("short_target_not_below_entry")
    if plan.fill_model.get("fill_policy") != "next_open":
        blockers.append("unsupported_fill_policy")
    if plan.fill_model.get("same_candle_ambiguity") != "conservative_stop_first":
        blockers.append("unsupported_same_candle_policy")
    return blockers


def try_fill_at_next_open(
    *,
    signal_bar_open_time: datetime,
    direction: str,
    fill_model: dict[str, Any],
    bars: list[CandleBar],
) -> FillOutcome:
    """Fill only at the first final bar whose open_time is strictly after the signal bar."""
    for bar in bars:
        if not bar.is_final:
            continue
        if bar.open_time <= signal_bar_open_time:
            continue
        price = entry_fill(bar.open, direction=direction, fill_model=fill_model)
        return FillOutcome(
            filled=True,
            entry_price=price,
            entry_bar_open_time=bar.open_time,
            note="filled_next_open",
        )
    return FillOutcome(filled=False, note="waiting_for_next_open")


def evaluate_exit_on_bar(
    bar: CandleBar,
    *,
    direction: str,
    entry_price: Decimal,
    stop: Decimal,
    target: Decimal,
    invalidation: Decimal | None,
    entry_bar_open_time: datetime,
    fill_model: dict[str, Any],
    qty: Decimal,
) -> ExitOutcome:
    """Evaluate one closed bar against an open paper trade. Conservative stop-first."""
    if not bar.is_final or bar.open_time <= entry_bar_open_time:
        return ExitOutcome(closed=False, note="bar_not_applicable")

    bars_held = 0  # caller tracks; returned for convenience when closing
    exit_price: Decimal | None = None
    exit_reason: str | None = None

    if direction == "long":
        hit_stop = bar.low <= stop
        hit_target = bar.high >= target
        if hit_stop and hit_target:
            exit_price, exit_reason = stop, "stop_target_same_bar_conservative"
        elif hit_stop:
            exit_price, exit_reason = stop, "stop"
        elif hit_target:
            exit_price, exit_reason = target, "target"
        elif invalidation is not None and bar.close < invalidation:
            exit_price, exit_reason = bar.close, "invalidation"
    else:
        hit_stop = bar.high >= stop
        hit_target = bar.low <= target
        if hit_stop and hit_target:
            exit_price, exit_reason = stop, "stop_target_same_bar_conservative"
        elif hit_stop:
            exit_price, exit_reason = stop, "stop"
        elif hit_target:
            exit_price, exit_reason = target, "target"
        elif invalidation is not None and bar.close > invalidation:
            exit_price, exit_reason = bar.close, "invalidation"

    # Timeout checked by caller with bars_held; support in-bar close when reason set.
    if exit_price is None:
        return ExitOutcome(closed=False)

    fill = exit_fill(exit_price, direction=direction, fill_model=fill_model)
    costs = round_trip_costs(
        entry=entry_price, exit_price=fill, qty=qty, fill_model=fill_model
    )
    if direction == "long":
        pnl = (fill - entry_price) * qty - costs
    else:
        pnl = (entry_price - fill) * qty - costs
    risk_per_unit = abs(entry_price - stop)
    realized_r = (pnl / (risk_per_unit * qty)) if risk_per_unit > 0 and qty > 0 else Decimal("0")
    return ExitOutcome(
        closed=True,
        exit_price=fill,
        exit_reason=exit_reason,
        exit_bar_open_time=bar.open_time,
        realized_pnl=pnl,
        realized_r=realized_r,
        costs=costs,
        bars_held=bars_held,
        note=PAPER_LABEL,
    )


def timeout_exit(
    bar: CandleBar,
    *,
    direction: str,
    entry_price: Decimal,
    stop: Decimal,
    fill_model: dict[str, Any],
    qty: Decimal,
    bars_held: int,
) -> ExitOutcome | None:
    if bars_held < max_bars(fill_model):
        return None
    fill = exit_fill(bar.close, direction=direction, fill_model=fill_model)
    costs = round_trip_costs(
        entry=entry_price, exit_price=fill, qty=qty, fill_model=fill_model
    )
    if direction == "long":
        pnl = (fill - entry_price) * qty - costs
    else:
        pnl = (entry_price - fill) * qty - costs
    risk_per_unit = abs(entry_price - stop)
    realized_r = (pnl / (risk_per_unit * qty)) if risk_per_unit > 0 and qty > 0 else Decimal("0")
    return ExitOutcome(
        closed=True,
        exit_price=fill,
        exit_reason="timeout",
        exit_bar_open_time=bar.open_time,
        realized_pnl=pnl,
        realized_r=realized_r,
        costs=costs,
        bars_held=bars_held,
        note=PAPER_LABEL,
    )


def journal_summary(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    exit_reason: str,
    realized_r: Decimal | None,
    realized_pnl: Decimal | None,
) -> str:
    r_text = "n/a" if realized_r is None else f"{realized_r.normalize():f}R"
    pnl_text = "n/a" if realized_pnl is None else f"{realized_pnl.normalize():f}"
    return (
        f"[PAPER] {symbol} {timeframe} {direction} closed via {exit_reason}: "
        f"{r_text} (pnl {pnl_text}). Decision support only — not a live fill."
    )
