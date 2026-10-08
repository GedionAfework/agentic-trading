from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_features.engine import FEATURE_ENGINE_VERSION, compute_feature
from private_trading_features.types import CandleBar
from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import RISK_ENGINE_VERSION, default_policy_config
from private_trading_risk.types import Direction as RiskDirection
from private_trading_risk.types import InstrumentRiskMeta, RiskInput
from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import STRATEGY_ENGINE_VERSION, evaluate_strategy
from private_trading_strategies.types import Direction, SetupState
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

from private_trading_backtest.costs import apply_entry_price, apply_exit_price, cost_amount
from private_trading_backtest.metrics import compute_metrics
from private_trading_backtest.types import (
    BacktestReport,
    CostModel,
    FillPolicy,
    OutcomeSource,
    SimulatedTrade,
)

BACKTEST_ENGINE_VERSION = "0.1.0"

_FEATURE_NAMES_LONG = (
    "bos_bullish",
    "bos_bearish",
    "significant_volume",
    "low_volume",
    "last_swing_high",
    "last_swing_low",
    "atr",
    "ema_htf_bias",
)


def _fv_payload(bars: list[CandleBar], index: int, name: str) -> dict[str, Any]:
    fv = compute_feature(name, bars, index)
    return {
        "status": fv.status.value,
        "value": float(fv.value) if isinstance(fv.value, Decimal) else fv.value,
        "reason": fv.reason,
    }


def run_replay(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    dataset_fingerprint: str,
    config: dict[str, Any] | None = None,
) -> BacktestReport:
    """Event-driven replay using live strategy/risk evaluators. No look-ahead fills."""
    cfg = {
        "fill_policy": FillPolicy.NEXT_OPEN.value,
        "same_candle_ambiguity": "conservative",
        "fee_bps": "10",
        "slippage_bps": "5",
        "spread_bps": "2",
        "outcome_label_source": OutcomeSource.BACKTEST.value,
        "advisory_definitions": ["WYK-001", "IMB-001", "SMT-001"],
        "min_rr": "2.0",
        "direction": "long",
        "account_equity": "10000",
        "qty": "1",
        "max_bars_in_trade": 40,
        "entry_path": DEFAULT_ENTRY_PATH,
    }
    if config:
        cfg.update(config)

    costs = CostModel(
        fee_bps=Decimal(str(cfg["fee_bps"])),
        slippage_bps=Decimal(str(cfg["slippage_bps"])),
        spread_bps=Decimal(str(cfg["spread_bps"])),
    )
    min_rr = Decimal(str(cfg["min_rr"]))
    direction = Direction(str(cfg["direction"]))
    qty = Decimal(str(cfg["qty"]))
    max_bars = int(cfg["max_bars_in_trade"])

    strategy = build_wyckoff_hdm_v1(
        version_no=1,
        advisory_definitions=list(cfg.get("advisory_definitions") or []),
    )
    risk_cfg = default_policy_config(min_rr=float(min_rr))

    trades: list[SimulatedTrade] = []
    notes: list[str] = [
        "fill_policy=next_open",
        "same_candle_ambiguity=conservative_stop_first",
        f"outcome_source={cfg['outcome_label_source']}",
    ]
    signals_seen = 0
    pending_entry: dict[str, Any] | None = None
    open_trade: dict[str, Any] | None = None
    trade_id = 0

    for i, bar in enumerate(bars):
        if not bar.is_final:
            continue

        # Manage open position on this bar (uses OHLC only — no future bars)
        if open_trade is not None:
            exit_price = None
            exit_reason = None
            stop = Decimal(str(open_trade["stop"]))
            target = Decimal(str(open_trade["target"]))
            d = open_trade["direction"]
            if d == "long":
                hit_stop = bar.low <= stop
                hit_target = bar.high >= target
                if hit_stop and hit_target:
                    exit_price, exit_reason = stop, "stop_target_same_bar_conservative"
                elif hit_stop:
                    exit_price, exit_reason = stop, "stop"
                elif hit_target:
                    exit_price, exit_reason = target, "target"
            else:
                hit_stop = bar.high >= stop
                hit_target = bar.low <= target
                if hit_stop and hit_target:
                    exit_price, exit_reason = stop, "stop_target_same_bar_conservative"
                elif hit_stop:
                    exit_price, exit_reason = stop, "stop"
                elif hit_target:
                    exit_price, exit_reason = target, "target"

            held = i - int(open_trade["entry_bar_index"])
            if exit_price is None and held >= max_bars:
                exit_price, exit_reason = bar.close, "timeout"

            if exit_price is not None:
                fill = apply_exit_price(exit_price, direction=d, costs=costs)
                entry = Decimal(str(open_trade["entry_price"]))
                risk = abs(entry - Decimal(str(open_trade["stop"])))
                if d == "long":
                    pnl = (fill - entry) * qty
                else:
                    pnl = (entry - fill) * qty
                cogs = cost_amount(entry * qty, costs=costs) + cost_amount(fill * qty, costs=costs)
                pnl -= cogs
                pnl_r = (pnl / (risk * qty)) if risk > 0 else Decimal("0")
                trade_id += 1
                trades.append(
                    SimulatedTrade(
                        trade_id=trade_id,
                        direction=d,
                        signal_bar_index=int(open_trade["signal_bar_index"]),
                        entry_bar_index=int(open_trade["entry_bar_index"]),
                        exit_bar_index=i,
                        entry_time=open_trade["entry_time"],
                        exit_time=bar.open_time,
                        entry_price=entry,
                        exit_price=fill,
                        stop_price=Decimal(str(open_trade["stop"])),
                        target_price=Decimal(str(open_trade["target"])),
                        qty=qty,
                        pnl=pnl,
                        pnl_r=pnl_r,
                        exit_reason=exit_reason or "exit",
                        costs=cogs,
                        outcome_source=str(cfg["outcome_label_source"]),
                    )
                )
                open_trade = None

        # Fill pending entry at this bar's open (signal was prior bar)
        if pending_entry is not None and open_trade is None:
            if i != int(pending_entry["entry_bar_index"]):
                # Should only fill on designated next bar
                pass
            else:
                raw_entry = bar.open
                d = pending_entry["direction"]
                entry = apply_entry_price(raw_entry, direction=d, costs=costs)
                open_trade = {
                    **pending_entry,
                    "entry_price": str(entry),
                    "entry_time": bar.open_time,
                }
                pending_entry = None

        # No new signals while in a trade or waiting to fill
        if open_trade is not None or pending_entry is not None:
            continue
        if i >= len(bars) - 1:
            # Cannot schedule next_open fill
            continue

        names = list(_FEATURE_NAMES_LONG)
        if str(cfg["entry_path"]) == "safer":
            names.extend(("retest_long", "retest_short"))
        features = {name: _fv_payload(bars, i, name) for name in names}
        ctx = build_playbook_context(
            bars,
            i,
            direction=direction,
            min_rr=min_rr,
            entry_path=str(cfg["entry_path"]),
        )
        assessment = evaluate_strategy(
            strategy,
            direction=direction,
            features=features,
            context={k: v for k, v in ctx.items() if not k.startswith("_")},
        )
        if assessment.setup_state != SetupState.READY_FOR_REVIEW:
            continue
        signals_seen += 1

        stop_s = ctx.get("_stop_price")
        entry_ref = Decimal(str(ctx["_entry_ref"]))
        if not stop_s:
            notes.append(f"signal@{i}_skipped_no_stop")
            continue
        stop = Decimal(str(stop_s))
        risk = abs(entry_ref - stop)
        if risk <= 0:
            continue
        target = entry_ref + (risk * min_rr) if direction == Direction.LONG else entry_ref - (
            risk * min_rr
        )

        risk_result = assess_risk(
            policy_code="default-crypto",
            policy_version_no=1,
            policy_config=risk_cfg,
            risk_input=RiskInput(
                direction=RiskDirection(direction.value),
                entry=entry_ref,
                stop=stop,
                target_1=target,
                data_fresh=True,
                market_actionable=True,
                account_equity=Decimal(str(cfg["account_equity"])),
                instrument=InstrumentRiskMeta(asset_class="crypto", qty_step=Decimal("0.001")),
            ),
        )
        if not risk_result.approved:
            notes.append(f"signal@{i}_risk_blocked:{','.join(risk_result.hard_blockers)}")
            continue

        # Schedule fill at next bar open — never current close (no look-ahead)
        pending_entry = {
            "direction": direction.value,
            "signal_bar_index": i,
            "entry_bar_index": i + 1,
            "stop": str(stop),
            "target": str(target),
        }

    # Force-close any open position at last bar for complete cohort metrics.
    if open_trade is not None and bars:
        i = len(bars) - 1
        bar = bars[i]
        d = open_trade["direction"]
        fill = apply_exit_price(bar.close, direction=d, costs=costs)
        entry = Decimal(str(open_trade["entry_price"]))
        risk = abs(entry - Decimal(str(open_trade["stop"])))
        if d == "long":
            pnl = (fill - entry) * qty
        else:
            pnl = (entry - fill) * qty
        cogs = cost_amount(entry * qty, costs=costs) + cost_amount(fill * qty, costs=costs)
        pnl -= cogs
        pnl_r = (pnl / (risk * qty)) if risk > 0 else Decimal("0")
        trade_id += 1
        trades.append(
            SimulatedTrade(
                trade_id=trade_id,
                direction=d,
                signal_bar_index=int(open_trade["signal_bar_index"]),
                entry_bar_index=int(open_trade["entry_bar_index"]),
                exit_bar_index=i,
                entry_time=open_trade["entry_time"],
                exit_time=bar.open_time,
                entry_price=entry,
                exit_price=fill,
                stop_price=Decimal(str(open_trade["stop"])),
                target_price=Decimal(str(open_trade["target"])),
                qty=qty,
                pnl=pnl,
                pnl_r=pnl_r,
                exit_reason="end_of_data",
                costs=cogs,
                outcome_source=str(cfg["outcome_label_source"]),
            )
        )
        notes.append("force_closed_open_trade_at_end")

    metrics = compute_metrics(trades, symbol=symbol, timeframe=timeframe)
    return BacktestReport(
        metrics=metrics,
        trades=trades,
        pins={
            "backtest_engine_version": BACKTEST_ENGINE_VERSION,
            "feature_engine_version": FEATURE_ENGINE_VERSION,
            "strategy_engine_version": STRATEGY_ENGINE_VERSION,
            "risk_engine_version": RISK_ENGINE_VERSION,
            "strategy_code": strategy.code,
            "strategy_version_no": strategy.version_no,
            "dataset_fingerprint": dataset_fingerprint,
            "fill_policy": cfg["fill_policy"],
            "resolution_policy": cfg["same_candle_ambiguity"],
            "outcome_label_source": cfg["outcome_label_source"],
        },
        config=cfg,
        bar_count=len(bars),
        signals_seen=signals_seen,
        notes=notes,
    )


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    return {
        "metrics": {
            "trade_count": report.metrics.trade_count,
            "win_count": report.metrics.win_count,
            "loss_count": report.metrics.loss_count,
            "win_rate": report.metrics.win_rate,
            "expectancy_r": report.metrics.expectancy_r,
            "total_pnl": str(report.metrics.total_pnl),
            "max_drawdown_pnl": str(report.metrics.max_drawdown_pnl),
            "slices": report.metrics.slices,
        },
        "trades": [
            {
                "trade_id": t.trade_id,
                "direction": t.direction,
                "signal_bar_index": t.signal_bar_index,
                "entry_bar_index": t.entry_bar_index,
                "exit_bar_index": t.exit_bar_index,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "stop_price": str(t.stop_price),
                "target_price": str(t.target_price),
                "qty": str(t.qty),
                "pnl": str(t.pnl),
                "pnl_r": str(t.pnl_r),
                "exit_reason": t.exit_reason,
                "costs": str(t.costs),
                "outcome_source": t.outcome_source,
            }
            for t in report.trades
        ],
        "pins": report.pins,
        "config": report.config,
        "bar_count": report.bar_count,
        "signals_seen": report.signals_seen,
        "notes": report.notes,
    }
