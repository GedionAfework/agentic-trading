"""Reusable, fail-closed walk-forward model selection for research challengers."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class ResearchObjective(StrEnum):
    PROFIT = "profit"
    WIN_RATE = "win_rate"


# Conservative fill degradation in basis points: slippage + half-spread.
# Forex uses price-only Yahoo OHLC, so these are research assumptions, not quotes.
PAIR_COST_BPS: dict[str, float] = {
    "BTC/USDT": 6.0,
    "ETH/USDT": 7.0,
    "BNB/USDT": 8.0,
    "SOL/USDT": 8.0,
    "DOGE/USDT": 12.0,
    "EUR/USD": 1.5,
    "GBP/USD": 2.0,
    "USD/JPY": 2.0,
    "USD/CHF": 3.0,
    "AUD/USD": 2.5,
    "USD/CAD": 2.5,
    "NZD/USD": 3.0,
    "EUR/GBP": 2.5,
}


def pair_cost_bps(symbol: str) -> float:
    if symbol in PAIR_COST_BPS:
        return PAIR_COST_BPS[symbol]
    return 8.0 if symbol.endswith("/USDT") else 3.0


@dataclass(slots=True, frozen=True)
class TimeFold:
    code: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    embargo_bars: int = 80
    bar_size: timedelta = timedelta(hours=1)

    @property
    def embargoed_train_end(self) -> datetime:
        return self.train_end - self.bar_size * self.embargo_bars

    def validate(self) -> None:
        if not (
            self.train_start < self.embargoed_train_end
            <= self.train_end
            <= self.test_start
            < self.test_end
        ):
            raise ValueError(f"invalid walk-forward fold: {self.code}")


@dataclass(slots=True)
class ResearchPerformance:
    outcomes_r: list[float] = field(default_factory=list)

    @property
    def trades(self) -> int:
        return len(self.outcomes_r)

    @property
    def wins(self) -> int:
        return sum(value > 0 for value in self.outcomes_r)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def mean_r(self) -> float:
        return sum(self.outcomes_r) / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(value for value in self.outcomes_r if value > 0)
        gross_loss = -sum(value for value in self.outcomes_r if value < 0)
        return gross_profit / gross_loss if gross_loss else float("inf")

    @property
    def max_drawdown_r(self) -> float:
        equity = peak = max_drawdown = 0.0
        for value in self.outcomes_r:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return max_drawdown

    @property
    def wilson_win_rate_lower(self) -> float:
        if not self.trades:
            return 0.0
        z = 1.96
        n = self.trades
        p = self.win_rate
        denominator = 1.0 + z * z / n
        centre = p + z * z / (2.0 * n)
        margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
        return (centre - margin) / denominator

    def extend(self, other: ResearchPerformance) -> None:
        self.outcomes_r.extend(other.outcomes_r)


@dataclass(slots=True, frozen=True)
class SelectionPolicy:
    objective: ResearchObjective
    min_trades: int = 40
    min_mean_r: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown_r: float = 20.0


@dataclass(slots=True)
class FoldSelection[ConfigT]:
    fold: TimeFold
    config: ConfigT | None
    training: ResearchPerformance
    test: ResearchPerformance
    rejection_reason: str | None = None


@dataclass(slots=True, frozen=True)
class PromotionDecision:
    approved: bool
    reasons: tuple[str, ...]
    combined: ResearchPerformance
    positive_period_fraction: float


def combine_performance(items: list[ResearchPerformance]) -> ResearchPerformance:
    combined = ResearchPerformance()
    for item in items:
        combined.extend(item)
    return combined


def eligible(result: ResearchPerformance, policy: SelectionPolicy) -> bool:
    return (
        result.trades >= policy.min_trades
        and result.mean_r > policy.min_mean_r
        and result.profit_factor > policy.min_profit_factor
        and result.max_drawdown_r <= policy.max_drawdown_r
    )


def selection_score(
    result: ResearchPerformance,
    objective: ResearchObjective,
    *,
    search_trials: int = 1,
) -> float:
    trial_penalty = math.sqrt(2.0 * math.log(max(search_trials, 1)))
    sample_penalty = (
        max(1.0, trial_penalty) / math.sqrt(result.trades)
        if result.trades
        else float("inf")
    )
    if objective == ResearchObjective.PROFIT:
        drawdown_penalty = result.max_drawdown_r / max(result.trades, 1)
        return result.mean_r - 0.1 * drawdown_penalty - sample_penalty
    return result.wilson_win_rate_lower + 0.1 * result.mean_r - sample_penalty


def select_config[ConfigT](
    candidates: list[tuple[ConfigT, ResearchPerformance]],
    policy: SelectionPolicy,
) -> tuple[ConfigT, ResearchPerformance] | None:
    passing = [
        (
            selection_score(
                result,
                policy.objective,
                search_trials=len(candidates),
            ),
            config,
            result,
        )
        for config, result in candidates
        if eligible(result, policy)
    ]
    if not passing:
        return None
    passing.sort(key=lambda row: row[0], reverse=True)
    _, config, result = passing[0]
    return config, result


def run_walk_forward[ConfigT](
    *,
    folds: list[TimeFold],
    configs: list[ConfigT],
    policy: SelectionPolicy,
    evaluate: Callable[[ConfigT, datetime, datetime], ResearchPerformance],
) -> list[FoldSelection[ConfigT]]:
    selections: list[FoldSelection[ConfigT]] = []
    for fold in folds:
        fold.validate()
        candidates = [
            (
                config,
                evaluate(config, fold.train_start, fold.embargoed_train_end),
            )
            for config in configs
        ]
        selected = select_config(candidates, policy)
        if selected is None:
            selections.append(
                FoldSelection(
                    fold=fold,
                    config=None,
                    training=ResearchPerformance(),
                    test=ResearchPerformance(),
                    rejection_reason="no_training_candidate_passed",
                )
            )
            continue
        config, training = selected
        test = evaluate(config, fold.test_start, fold.test_end)
        selections.append(
            FoldSelection(
                fold=fold,
                config=config,
                training=training,
                test=test,
            )
        )
    return selections


def evaluate_promotion(
    periods: list[ResearchPerformance],
    *,
    min_total_trades: int,
    min_mean_r: float = 0.0,
    min_profit_factor: float = 1.0,
    max_drawdown_r: float = 20.0,
    min_positive_period_fraction: float = 0.6,
    incumbent_mean_r: float | None = None,
    incumbent_win_rate: float | None = None,
) -> PromotionDecision:
    combined = combine_performance(periods)
    populated = [period for period in periods if period.trades]
    positive_fraction = (
        sum(period.mean_r > 0 for period in populated) / len(populated)
        if populated
        else 0.0
    )
    reasons: list[str] = []
    if combined.trades < min_total_trades:
        reasons.append("insufficient_total_trades")
    if combined.mean_r <= min_mean_r:
        reasons.append("non_positive_expectancy")
    if combined.profit_factor <= min_profit_factor:
        reasons.append("profit_factor_not_above_one")
    if combined.max_drawdown_r > max_drawdown_r:
        reasons.append("drawdown_limit_exceeded")
    if positive_fraction < min_positive_period_fraction:
        reasons.append("insufficient_positive_periods")
    if incumbent_mean_r is not None and combined.mean_r <= incumbent_mean_r:
        reasons.append("did_not_beat_incumbent_expectancy")
    if incumbent_win_rate is not None and combined.win_rate <= incumbent_win_rate:
        reasons.append("did_not_beat_incumbent_win_rate")
    return PromotionDecision(
        approved=not reasons,
        reasons=tuple(reasons),
        combined=combined,
        positive_period_fraction=positive_fraction,
    )
