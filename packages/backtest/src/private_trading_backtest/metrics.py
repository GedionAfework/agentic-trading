from __future__ import annotations

from decimal import Decimal

from private_trading_backtest.types import BacktestMetrics, SimulatedTrade


def compute_metrics(trades: list[SimulatedTrade], *, symbol: str, timeframe: str) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(
            trade_count=0,
            win_count=0,
            loss_count=0,
            win_rate=None,
            expectancy_r=None,
            total_pnl=Decimal("0"),
            max_drawdown_pnl=Decimal("0"),
            slices={"symbol": {symbol: 0}, "timeframe": {timeframe: 0}},
        )

    wins = [t for t in trades if t.pnl_r > 0]
    losses = [t for t in trades if t.pnl_r <= 0]
    total_pnl = sum((t.pnl for t in trades), Decimal("0"))
    expectancy_r = float(sum((t.pnl_r for t in trades), Decimal("0")) / Decimal(len(trades)))

    equity = Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    for t in trades:
        equity += t.pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return BacktestMetrics(
        trade_count=len(trades),
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=len(wins) / len(trades),
        expectancy_r=expectancy_r,
        total_pnl=total_pnl,
        max_drawdown_pnl=max_dd,
        slices={
            "symbol": {symbol: len(trades)},
            "timeframe": {timeframe: len(trades)},
            "exit_reason": _count_by(trades, key="exit_reason"),
            "outcome_source": _count_by(trades, key="outcome_source"),
        },
    )


def _count_by(trades: list[SimulatedTrade], *, key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in trades:
        val = str(getattr(t, key))
        out[val] = out.get(val, 0) + 1
    return out
