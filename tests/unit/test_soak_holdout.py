from datetime import UTC, datetime

from private_trading_paper_trade.holdout import evaluate_holdout_review
from private_trading_paper_trade.soak_metrics import ClosedSoakTrade


def _trade(r: float, year: int, month: int, day: int = 15) -> ClosedSoakTrade:
    return ClosedSoakTrade(
        realized_r=r,
        closed_at=datetime(year, month, day, tzinfo=UTC),
        extra_cost_bps_vs_research=0.5,
    )


def test_holdout_ignores_pre_freeze_trades_and_stays_wait() -> None:
    old = [_trade(2.0, 2026, 6) for _ in range(100)]
    result = evaluate_holdout_review(old, step2_complete=True)
    assert result["closed_trades"] == 0
    assert result["decision"] == "WAIT"
    assert "enough_trades" in result["blocking_gates"]


def test_holdout_requires_step2_and_competitive_mean_r() -> None:
    trades: list[ClosedSoakTrade] = []
    for month in (10, 11, 12):
        trades.extend([_trade(0.05, 2026, month) for _ in range(20)])
        trades.extend([_trade(-0.04, 2026, month) for _ in range(10)])
    blocked = evaluate_holdout_review(trades, step2_complete=False)
    assert blocked["decision"] == "WAIT"
    assert "step2_complete" in blocked["blocking_gates"]

    weak = evaluate_holdout_review(trades, step2_complete=True)
    assert weak["mean_r"] > 0
    assert "competitive_vs_research" in weak["blocking_gates"]


def test_holdout_can_pass_on_post_freeze_sample() -> None:
    trades: list[ClosedSoakTrade] = []
    for month in (10, 11, 12):
        day = 10 if month == 10 else 15
        trades.extend([_trade(0.5, 2026, month, day) for _ in range(20)])
        trades.extend([_trade(0.3, 2026, month, day) for _ in range(10)])
        trades.extend([_trade(-0.2, 2026, month, day) for _ in range(5)])
    # October 1–7 are before freeze; only day>=8 counts for month 10.
    result = evaluate_holdout_review(trades, step2_complete=True)
    assert result["closed_trades"] >= 80
    assert result["decision"] == "PASS"
    assert result["approved_for_paper_promotion"] is True
    assert result["blocking_gates"] == []
