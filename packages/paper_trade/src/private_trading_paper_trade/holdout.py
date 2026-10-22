"""Step 3 holdout review for the frozen soak incumbent.

Uses only paper trades closed after the soak freeze. Historical 2022–2026 is
spent for SOL V1 and must not be recycled as an untouched holdout.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from private_trading_strategies.soak_freeze import (
    SOAK_HOLDOUT_MIN_MEAN_R_FRACTION_OF_RESEARCH,
    SOAK_HOLDOUT_START,
    SOAK_RESEARCH_MEAN_R,
    SOAK_RESEARCH_WIN_RATE,
    SOAK_STEP2_MAX_DRAWDOWN_R,
    SOAK_STEP2_MAX_EXTRA_COST_BPS,
    SOAK_STEP2_MIN_CLOSED_TRADES,
    SOAK_STEP2_MIN_MEAN_R,
    SOAK_STEP2_MIN_POSITIVE_MONTH_FRACTION,
    SOAK_STEP2_MIN_PROFIT_FACTOR,
    SOAK_STEP2_MIN_TRADES_PER_MONTH,
    SOAK_SYMBOL,
    soak_incumbent,
)

from private_trading_paper_trade.soak_metrics import ClosedSoakTrade, evaluate_soak_sample


def holdout_start() -> datetime:
    return datetime.fromisoformat(SOAK_HOLDOUT_START).replace(tzinfo=UTC)


def filter_holdout_trades(trades: list[ClosedSoakTrade]) -> list[ClosedSoakTrade]:
    start = holdout_start()
    return [
        trade
        for trade in trades
        if trade.closed_at is not None and trade.closed_at >= start
    ]


def evaluate_holdout_review(
    trades: list[ClosedSoakTrade],
    *,
    step2_complete: bool,
) -> dict[str, Any]:
    """Score frozen soak trades on the unused paper window only."""
    incumbent = soak_incumbent()
    holdout = filter_holdout_trades(trades)
    sample = evaluate_soak_sample(
        holdout,
        min_closed_trades=SOAK_STEP2_MIN_CLOSED_TRADES,
        min_mean_r=SOAK_STEP2_MIN_MEAN_R,
        min_profit_factor=SOAK_STEP2_MIN_PROFIT_FACTOR,
        max_drawdown_r_limit=SOAK_STEP2_MAX_DRAWDOWN_R,
        min_positive_month_fraction=SOAK_STEP2_MIN_POSITIVE_MONTH_FRACTION,
        min_trades_per_month=SOAK_STEP2_MIN_TRADES_PER_MONTH,
        max_extra_cost_bps=SOAK_STEP2_MAX_EXTRA_COST_BPS,
        research_mean_r=SOAK_RESEARCH_MEAN_R,
        research_win_rate=SOAK_RESEARCH_WIN_RATE,
    )
    competitive_floor = (
        SOAK_RESEARCH_MEAN_R * SOAK_HOLDOUT_MIN_MEAN_R_FRACTION_OF_RESEARCH
    )
    mean_r = float(sample["mean_r"])
    competitive = mean_r >= competitive_floor
    gates = dict(sample["gates"])
    gates["step2_complete"] = step2_complete
    gates["competitive_vs_research"] = competitive
    blocking = [name for name, ok in gates.items() if not ok]
    approved = not blocking
    return {
        "symbol": SOAK_SYMBOL,
        "model_code": incumbent.code,
        "objective": incumbent.objective.value,
        "holdout_start": SOAK_HOLDOUT_START,
        "holdout_source": "paper_trades_after_freeze",
        "selection_data_through": "2025-12-31",
        "note": (
            "Holdout is closed SOL paper trades on/after the soak freeze. "
            "Do not recycle 2022–2026 walk-forward years as untouched."
        ),
        "competitive_mean_r_floor": competitive_floor,
        "research_mean_r": SOAK_RESEARCH_MEAN_R,
        **sample,
        "gates": gates,
        "all_gates_passed": approved,
        "blocking_gates": blocking,
        "step3_complete": approved,
        "approved_for_paper_promotion": approved,
        "decision": "PASS" if approved else "WAIT",
    }
