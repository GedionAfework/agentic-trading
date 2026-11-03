"""Score agentic vs deterministic decision path on next-open fills.

Not an edge claim — measures whether AG-01 trading outcomes match the
authoritative path, and reports measured P&L / R on the dataset used.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from private_trading_agents.agent_runtime import agent_session
from private_trading_agents.contracts import AgentId
from private_trading_agents.orchestrator import ag01_budget
from private_trading_agents.workflow import DecisionAction, run_decision_workflow
from private_trading_backtest.costs import apply_entry_price, apply_exit_price, cost_amount
from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import (
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_backtest.metrics import compute_metrics
from private_trading_backtest.replay import run_replay
from private_trading_backtest.types import CostModel, OutcomeSource, SimulatedTrade
from private_trading_features.types import CandleBar

Mode = Literal["deterministic", "agentic"]


def simulate_decision_path(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    mode: Mode,
    max_bars_in_trade: int = 40,
) -> dict[str, Any]:
    costs = CostModel(
        fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
        spread_bps=Decimal("2"),
    )
    qty = Decimal("1")
    trades: list[SimulatedTrade] = []
    enters = 0
    pending: dict[str, Any] | None = None
    open_trade: dict[str, Any] | None = None
    trade_id = 0

    for i, bar in enumerate(bars):
        if open_trade is not None:
            stop = Decimal(str(open_trade["stop"]))
            target = Decimal(str(open_trade["target"]))
            hit_stop = bar.low <= stop
            hit_target = bar.high >= target
            exit_price = None
            exit_reason = None
            if hit_stop and hit_target:
                exit_price, exit_reason = stop, "stop_target_same_bar_conservative"
            elif hit_stop:
                exit_price, exit_reason = stop, "stop"
            elif hit_target:
                exit_price, exit_reason = target, "target"
            elif i - int(open_trade["entry_bar_index"]) >= max_bars_in_trade:
                exit_price, exit_reason = bar.close, "timeout"
            if exit_price is not None:
                fill = apply_exit_price(exit_price, direction="long", costs=costs)
                entry = Decimal(str(open_trade["entry_price"]))
                risk = abs(entry - stop)
                pnl = (fill - entry) * qty
                cogs = cost_amount(entry * qty, costs=costs) + cost_amount(
                    fill * qty, costs=costs
                )
                pnl -= cogs
                pnl_r = (pnl / (risk * qty)) if risk > 0 else Decimal("0")
                trade_id += 1
                trades.append(
                    SimulatedTrade(
                        trade_id=trade_id,
                        direction="long",
                        signal_bar_index=int(open_trade["signal_bar_index"]),
                        entry_bar_index=int(open_trade["entry_bar_index"]),
                        exit_bar_index=i,
                        entry_time=open_trade["entry_time"],
                        exit_time=bar.open_time,
                        entry_price=entry,
                        exit_price=fill,
                        stop_price=stop,
                        target_price=target,
                        qty=qty,
                        pnl=pnl,
                        pnl_r=pnl_r,
                        exit_reason=exit_reason or "exit",
                        costs=cogs,
                        outcome_source=OutcomeSource.BACKTEST.value,
                    )
                )
                open_trade = None

        if pending is not None and open_trade is None:
            if i == int(pending["entry_bar_index"]):
                entry = apply_entry_price(bar.open, direction="long", costs=costs)
                open_trade = {
                    **pending,
                    "entry_price": str(entry),
                    "entry_time": bar.open_time,
                }
                pending = None
            continue

        if open_trade is not None or pending is not None:
            continue
        if i >= len(bars) - 1:
            continue

        with agent_session(budgets={AgentId.AG01_ORCHESTRATOR: ag01_budget()}):
            snap = run_decision_workflow(
                bars,
                symbol=symbol,
                timeframe=timeframe,
                bar_index=i,
                mode=mode,
            )
        if (
            snap.action == DecisionAction.ENTER
            and snap.stop_price is not None
            and snap.target_price is not None
        ):
            enters += 1
            pending = {
                "signal_bar_index": i,
                "entry_bar_index": i + 1,
                "stop": str(snap.stop_price),
                "target": str(snap.target_price),
            }

    # Force-close any open position at last close (measured end-of-sample).
    if open_trade is not None and bars:
        i = len(bars) - 1
        bar = bars[i]
        stop = Decimal(str(open_trade["stop"]))
        target = Decimal(str(open_trade["target"]))
        fill = apply_exit_price(bar.close, direction="long", costs=costs)
        entry = Decimal(str(open_trade["entry_price"]))
        risk = abs(entry - stop)
        pnl = (fill - entry) * qty
        cogs = cost_amount(entry * qty, costs=costs) + cost_amount(fill * qty, costs=costs)
        pnl -= cogs
        pnl_r = (pnl / (risk * qty)) if risk > 0 else Decimal("0")
        trade_id += 1
        trades.append(
            SimulatedTrade(
                trade_id=trade_id,
                direction="long",
                signal_bar_index=int(open_trade["signal_bar_index"]),
                entry_bar_index=int(open_trade["entry_bar_index"]),
                exit_bar_index=i,
                entry_time=open_trade["entry_time"],
                exit_time=bar.open_time,
                entry_price=entry,
                exit_price=fill,
                stop_price=stop,
                target_price=target,
                qty=qty,
                pnl=pnl,
                pnl_r=pnl_r,
                exit_reason="end_of_sample",
                costs=cogs,
                outcome_source=OutcomeSource.BACKTEST.value,
            )
        )

    metrics = compute_metrics(trades, symbol=symbol, timeframe=timeframe)
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return {
        "mode": mode,
        "bars": len(bars),
        "enter_signals": enters,
        "closed_trades": metrics.trade_count,
        "wins": metrics.win_count,
        "losses": metrics.loss_count,
        "win_rate": metrics.win_rate,
        "expectancy_r": metrics.expectancy_r,
        "total_pnl": str(metrics.total_pnl),
        "max_drawdown_pnl": str(metrics.max_drawdown_pnl),
        "exit_reasons": reasons,
        "trade_fingerprints": [
            (t.signal_bar_index, t.entry_bar_index, str(t.pnl_r), t.exit_reason)
            for t in trades
        ],
    }


def main() -> None:
    bars = frozen_bos_long_fixture()
    det = simulate_decision_path(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, mode="deterministic"
    )
    agt = simulate_decision_path(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, mode="agentic"
    )
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    classic = run_replay(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        dataset_fingerprint=fp,
    )
    cm = classic.metrics

    print("=== AG-01 decision-path trading (frozen_bos fixture) ===")
    for row in (det, agt):
        print(
            f"{row['mode']}: enters={row['enter_signals']} closed={row['closed_trades']} "
            f"win_rate={row['win_rate']} expectancy_r={row['expectancy_r']} "
            f"pnl={row['total_pnl']} exits={row['exit_reasons']}"
        )
    identical = det["trade_fingerprints"] == agt["trade_fingerprints"]
    print(f"agentic_matches_deterministic_trades: {identical}")
    print("=== classic strategy replay (same fixture, no AG-01 loop) ===")
    print(
        f"signals={classic.signals_seen} closed={cm.trade_count} "
        f"win_rate={cm.win_rate} expectancy_r={cm.expectancy_r} pnl={cm.total_pnl}"
    )


if __name__ == "__main__":
    main()
