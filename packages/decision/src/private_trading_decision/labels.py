from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_backtest.costs import apply_entry_price, apply_exit_price, cost_amount
from private_trading_backtest.types import CostModel
from private_trading_features.engine import compute_feature, get_feature
from private_trading_features.types import CandleBar, TriState
from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import evaluate_strategy
from private_trading_strategies.types import Direction, SetupState
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

from private_trading_decision.types import LabelClass, LabelPolicy, TrainingRow

FEATURE_NAMES = (
    "bos_bullish",
    "bos_bearish",
    "significant_volume",
    "low_volume",
    "last_swing_high",
    "last_swing_low",
    "atr",
    "volume_ratio",
    "range_vs_atr",
    "ema_50",
    "ema_htf_bias",
    "retest_long",
    "retest_short",
)


def feature_schema() -> dict[str, Any]:
    schema: dict[str, Any] = {}
    for name in FEATURE_NAMES:
        spec = get_feature(name)
        schema[name] = {
            "version": spec.version,
            "lookback": spec.lookback,
            "definition_id": spec.definition_id,
            "lock_status": spec.lock_status,
        }
    return schema


def _fv(bars: list[CandleBar], index: int, name: str) -> dict[str, Any]:
    fv = compute_feature(name, bars, index)
    value: Any = fv.value
    if isinstance(value, Decimal):
        value = float(value)
    return {"status": fv.status.value, "value": value, "reason": fv.reason}


def _stop_target(
    bars: list[CandleBar],
    index: int,
    *,
    direction: Direction,
    min_rr: Decimal,
) -> tuple[Decimal | None, Decimal | None, Decimal]:
    close = bars[index].close
    atr = compute_feature("atr", bars, index)
    if direction == Direction.LONG:
        swing = compute_feature("last_swing_low", bars, index)
        stop = swing.value if swing.status == TriState.TRUE else None
        if stop is None and atr.status == TriState.TRUE and atr.value:
            stop = close - Decimal(str(atr.value))
        if stop is None or stop >= close:
            return None, None, close
        risk = close - stop
        target = close + risk * min_rr
        return Decimal(str(stop)), target, close
    swing = compute_feature("last_swing_high", bars, index)
    stop = swing.value if swing.status == TriState.TRUE else None
    if stop is None and atr.status == TriState.TRUE and atr.value:
        stop = close + Decimal(str(atr.value))
    if stop is None or stop <= close:
        return None, None, close
    risk = stop - close
    target = close - risk * min_rr
    return Decimal(str(stop)), target, close


def _simulate_forward(
    bars: list[CandleBar],
    *,
    signal_index: int,
    direction: Direction,
    stop: Decimal,
    target: Decimal,
    costs: CostModel,
    horizon_bars: int,
) -> tuple[LabelClass, Decimal | None, str | None, int | None, int | None]:
    """Shared fill/exit semantics with backtest (next_open, conservative same-bar)."""
    entry_index = signal_index + 1
    if entry_index >= len(bars):
        return LabelClass.SKIPPED, None, "no_entry_bar", None, None

    entry_raw = bars[entry_index].open
    entry = apply_entry_price(entry_raw, direction=direction.value, costs=costs)
    end = min(len(bars) - 1, entry_index + horizon_bars)

    for j in range(entry_index, end + 1):
        bar = bars[j]
        exit_price = None
        exit_reason = None
        if direction == Direction.LONG:
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

        if exit_price is None and j == end:
            exit_price, exit_reason = bar.close, "horizon_end"

        if exit_price is not None:
            fill = apply_exit_price(exit_price, direction=direction.value, costs=costs)
            risk = abs(entry - stop)
            if direction == Direction.LONG:
                pnl = fill - entry
            else:
                pnl = entry - fill
            cogs = cost_amount(entry, costs=costs) + cost_amount(fill, costs=costs)
            pnl -= cogs
            pnl_r = (pnl / risk) if risk > 0 else Decimal("0")
            label = LabelClass.WIN if pnl_r > 0 else LabelClass.LOSS
            return label, pnl_r, exit_reason, entry_index, j

    return LabelClass.SKIPPED, None, "no_exit", entry_index, None


def label_bar(
    bars: list[CandleBar],
    index: int,
    *,
    symbol: str,
    timeframe: str,
    policy: LabelPolicy,
) -> TrainingRow:
    direction = Direction(policy.direction)
    strategy = build_wyckoff_hdm_v1(
        version_no=policy.strategy_version_no,
        advisory_definitions=list(policy.advisory_definitions),
    )
    features = {name: _fv(bars, index, name) for name in FEATURE_NAMES}
    feature_versions = {name: get_feature(name).version for name in FEATURE_NAMES}

    min_rr = Decimal(policy.min_rr)
    stop, target, entry_ref = _stop_target(bars, index, direction=direction, min_rr=min_rr)
    ctx = build_playbook_context(
        bars, index, direction=direction, min_rr=min_rr, entry_path=DEFAULT_ENTRY_PATH
    )
    assessment = evaluate_strategy(
        strategy,
        direction=direction,
        features=features,
        context={k: v for k, v in ctx.items() if not k.startswith("_")},
    )

    costs = CostModel(
        fee_bps=Decimal(policy.fee_bps),
        slippage_bps=Decimal(policy.slippage_bps),
        spread_bps=Decimal(policy.spread_bps),
    )

    label = LabelClass.SKIPPED
    pnl_r: Decimal | None = None
    exit_reason: str | None = None
    entry_i: int | None = None
    exit_i: int | None = None

    if assessment.setup_state == SetupState.NO_SETUP:
        label = LabelClass.NO_SETUP
    elif assessment.setup_state in {
        SetupState.WAIT,
        SetupState.WATCH,
        SetupState.WAIT_FOR_CONFIRMATION,
    }:
        label = LabelClass.WAIT
    elif assessment.setup_state == SetupState.READY_FOR_REVIEW:
        if stop is None or target is None:
            label = LabelClass.SKIPPED
            exit_reason = "missing_stop_or_target"
        elif index + 1 + policy.horizon_bars > len(bars) - 1 and index + 1 >= len(bars):
            label = LabelClass.SKIPPED
            exit_reason = "insufficient_horizon"
        else:
            label, pnl_r, exit_reason, entry_i, exit_i = _simulate_forward(
                bars,
                signal_index=index,
                direction=direction,
                stop=stop,
                target=target,
                costs=costs,
                horizon_bars=policy.horizon_bars,
            )
    else:
        label = LabelClass.WAIT

    return TrainingRow(
        row_id=f"{symbol}:{timeframe}:{index}:{bars[index].open_time.isoformat()}",
        bar_index=index,
        open_time=bars[index].open_time,
        symbol=symbol,
        timeframe=timeframe,
        features=features,
        feature_versions=feature_versions,
        setup_state=assessment.setup_state.value,
        direction=direction.value,
        label=label,
        pnl_r=pnl_r,
        exit_reason=exit_reason,
        entry_bar_index=entry_i,
        exit_bar_index=exit_i,
        strategy_code=policy.strategy_code,
        strategy_version_no=policy.strategy_version_no,
        label_policy_id=policy.policy_id,
        label_policy_version=policy.version,
        outcome_source=policy.outcome_source,
        source_bar_open_time=bars[index].open_time,
        meta={"entry_ref": str(entry_ref), "blockers": assessment.blockers},
    )
