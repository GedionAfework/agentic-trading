"""Pure soak progress metrics — no DB, no look-ahead."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class ClosedSoakTrade:
    realized_r: float
    closed_at: datetime | None
    extra_cost_bps_vs_research: float | None = None


def profit_factor(outcomes_r: list[float]) -> float | None:
    if not outcomes_r:
        return None
    gross_profit = sum(value for value in outcomes_r if value > 0)
    gross_loss = -sum(value for value in outcomes_r if value < 0)
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else None
    return gross_profit / gross_loss


def max_drawdown_r(outcomes_r: list[float]) -> float:
    equity = peak = max_dd = 0.0
    for value in outcomes_r:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def positive_month_fraction(
    trades: list[ClosedSoakTrade],
    *,
    min_trades_per_month: int,
) -> tuple[float | None, int, int]:
    """Return (fraction, positive_months, eligible_months)."""
    by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
    for trade in trades:
        if trade.closed_at is None or trade.realized_r is None:
            continue
        key = (trade.closed_at.year, trade.closed_at.month)
        by_month[key].append(trade.realized_r)
    eligible = {
        month: values
        for month, values in by_month.items()
        if len(values) >= min_trades_per_month
    }
    if not eligible:
        return None, 0, 0
    positive = sum(sum(values) > 0 for values in eligible.values())
    return positive / len(eligible), positive, len(eligible)


def evaluate_soak_sample(
    trades: list[ClosedSoakTrade],
    *,
    min_closed_trades: int,
    min_mean_r: float,
    min_profit_factor: float,
    max_drawdown_r_limit: float,
    min_positive_month_fraction: float,
    min_trades_per_month: int,
    max_extra_cost_bps: float,
    research_mean_r: float,
    research_win_rate: float,
) -> dict[str, Any]:
    outcomes = [trade.realized_r for trade in trades]
    n = len(outcomes)
    wins = sum(value > 0 for value in outcomes)
    mean_r = sum(outcomes) / n if n else 0.0
    pf = profit_factor(outcomes)
    dd = max_drawdown_r(outcomes)
    month_fraction, positive_months, eligible_months = positive_month_fraction(
        trades, min_trades_per_month=min_trades_per_month
    )
    extras = [
        trade.extra_cost_bps_vs_research
        for trade in trades
        if trade.extra_cost_bps_vs_research is not None
    ]
    avg_extra = sum(extras) / len(extras) if extras else None

    gates = {
        "enough_trades": n >= min_closed_trades,
        "positive_mean_r": mean_r > min_mean_r,
        "profit_factor": pf is not None and pf > min_profit_factor,
        "drawdown": dd <= max_drawdown_r_limit,
        "monthly_consistency": (
            month_fraction is not None
            and month_fraction >= min_positive_month_fraction
        ),
        "fill_gap": avg_extra is not None and avg_extra < max_extra_cost_bps,
    }
    return {
        "closed_trades": n,
        "min_closed_trades": min_closed_trades,
        "win_rate": None if not n else wins / n,
        "mean_r": mean_r,
        "profit_factor": pf,
        "max_drawdown_r": dd,
        "positive_month_fraction": month_fraction,
        "positive_months": positive_months,
        "eligible_months": eligible_months,
        "min_trades_per_month": min_trades_per_month,
        "avg_extra_cost_bps_vs_research": avg_extra,
        "max_extra_cost_bps": max_extra_cost_bps,
        "research_mean_r": research_mean_r,
        "research_win_rate": research_win_rate,
        "gates": gates,
        "all_gates_passed": all(gates.values()),
        "blocking_gates": [name for name, ok in gates.items() if not ok],
    }
