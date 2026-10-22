from datetime import UTC, datetime

from private_trading_paper_trade.soak_metrics import (
    ClosedSoakTrade,
    evaluate_soak_sample,
    positive_month_fraction,
)


def _trade(r: float, year: int, month: int, *, extra: float | None = 0.5) -> ClosedSoakTrade:
    return ClosedSoakTrade(
        realized_r=r,
        closed_at=datetime(year, month, 15, tzinfo=UTC),
        extra_cost_bps_vs_research=extra,
    )


def test_step2_gates_fail_until_sample_and_consistency_exist() -> None:
    thin = [_trade(1.0, 2026, 1)] * 10
    early = evaluate_soak_sample(
        thin,
        min_closed_trades=80,
        min_mean_r=0.0,
        min_profit_factor=1.1,
        max_drawdown_r_limit=20.0,
        min_positive_month_fraction=0.6,
        min_trades_per_month=4,
        max_extra_cost_bps=2.0,
        research_mean_r=0.215,
        research_win_rate=0.409,
    )
    assert early["all_gates_passed"] is False
    assert "enough_trades" in early["blocking_gates"]


def test_step2_gates_pass_on_consistent_positive_sample() -> None:
    trades: list[ClosedSoakTrade] = []
    for month in range(1, 5):
        trades.extend([_trade(0.5, 2026, month), _trade(0.4, 2026, month)] * 10)
        trades.extend([_trade(-0.2, 2026, month)] * 5)
    result = evaluate_soak_sample(
        trades,
        min_closed_trades=80,
        min_mean_r=0.0,
        min_profit_factor=1.1,
        max_drawdown_r_limit=20.0,
        min_positive_month_fraction=0.6,
        min_trades_per_month=4,
        max_extra_cost_bps=2.0,
        research_mean_r=0.215,
        research_win_rate=0.409,
    )
    assert result["closed_trades"] >= 80
    assert result["mean_r"] > 0
    assert result["profit_factor"] is not None and result["profit_factor"] > 1.1
    assert result["all_gates_passed"] is True
    assert result["blocking_gates"] == []


def test_positive_month_fraction_ignores_thin_months() -> None:
    trades = [
        _trade(1.0, 2026, 1),
        _trade(1.0, 2026, 1),
        _trade(-1.0, 2026, 2),
        _trade(-1.0, 2026, 2),
        _trade(-1.0, 2026, 2),
        _trade(-1.0, 2026, 2),
    ]
    fraction, positive, eligible = positive_month_fraction(
        trades, min_trades_per_month=4
    )
    assert eligible == 1
    assert positive == 0
    assert fraction == 0.0
