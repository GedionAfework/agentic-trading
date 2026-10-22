from datetime import UTC, datetime, timedelta

from private_trading_backtest.walkforward import (
    ResearchObjective,
    ResearchPerformance,
    SelectionPolicy,
    TimeFold,
    evaluate_promotion,
    pair_cost_bps,
    run_walk_forward,
    select_config,
)


def test_profit_and_win_rate_objectives_can_select_different_configs() -> None:
    high_profit = ResearchPerformance([2.0, 2.0, -1.0, -1.0] * 15)
    high_wins = ResearchPerformance([0.3, 0.3, 0.3, -0.5] * 15)

    profit = select_config(
        [("profit", high_profit), ("wins", high_wins)],
        SelectionPolicy(ResearchObjective.PROFIT, min_trades=40),
    )
    wins = select_config(
        [("profit", high_profit), ("wins", high_wins)],
        SelectionPolicy(ResearchObjective.WIN_RATE, min_trades=40),
    )

    assert profit is not None and profit[0] == "profit"
    assert wins is not None and wins[0] == "wins"


def test_walk_forward_embargoes_training_and_fails_closed() -> None:
    fold = TimeFold(
        code="2025",
        train_start=datetime(2023, 1, 1, tzinfo=UTC),
        train_end=datetime(2025, 1, 1, tzinfo=UTC),
        test_start=datetime(2025, 1, 1, tzinfo=UTC),
        test_end=datetime(2026, 1, 1, tzinfo=UTC),
        embargo_bars=80,
    )
    calls: list[tuple[datetime, datetime]] = []

    def evaluate(_config: str, start: datetime, end: datetime) -> ResearchPerformance:
        calls.append((start, end))
        return ResearchPerformance([-1.0] * 50)

    selections = run_walk_forward(
        folds=[fold],
        configs=["loser"],
        policy=SelectionPolicy(ResearchObjective.PROFIT, min_trades=40),
        evaluate=evaluate,
    )

    assert calls[0][1] == fold.train_end - timedelta(hours=80)
    assert selections[0].config is None
    assert selections[0].rejection_reason == "no_training_candidate_passed"


def test_promotion_requires_consistency_not_only_positive_aggregate() -> None:
    decision = evaluate_promotion(
        [
            ResearchPerformance([3.0] * 20),
            ResearchPerformance([-1.0] * 20),
            ResearchPerformance([-1.0] * 20),
        ],
        min_total_trades=50,
        min_positive_period_fraction=0.6,
    )
    assert decision.combined.mean_r > 0
    assert decision.approved is False
    assert "insufficient_positive_periods" in decision.reasons


def test_pair_costs_are_tighter_for_liquid_fx_than_altcoins() -> None:
    assert pair_cost_bps("EUR/USD") < pair_cost_bps("SOL/USDT")
    assert pair_cost_bps("BTC/USDT") < pair_cost_bps("SOL/USDT")


def test_walk_forward_selects_among_strategy_families() -> None:
    fold = TimeFold(
        code="2025",
        train_start=datetime(2023, 1, 1, tzinfo=UTC),
        train_end=datetime(2025, 1, 1, tzinfo=UTC),
        test_start=datetime(2025, 1, 1, tzinfo=UTC),
        test_end=datetime(2026, 1, 1, tzinfo=UTC),
        embargo_bars=80,
    )

    def evaluate(config: str, start: datetime, end: datetime) -> ResearchPerformance:
        if end.year < 2025:
            if config == "trend_breakout":
                return ResearchPerformance([-1.0] * 50)
            return ResearchPerformance([1.0, 0.5, -0.2] * 20)
        return ResearchPerformance([0.4] * 40)

    selections = run_walk_forward(
        folds=[fold],
        configs=["trend_breakout", "session_pullback"],
        policy=SelectionPolicy(ResearchObjective.PROFIT, min_trades=40),
        evaluate=evaluate,
    )

    assert selections[0].config == "session_pullback"
    assert selections[0].test.trades == 40
