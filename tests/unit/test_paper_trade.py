from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.types import CandleBar
from private_trading_paper_trade.engine import (
    PaperPlan,
    evaluate_exit_on_bar,
    timeout_exit,
    try_fill_at_next_open,
    validate_plan,
)
from private_trading_paper_trade.fill_model import PAPER_LABEL, default_fill_model


def _bar(i: int, *, o="100", h="110", low="90", c="105", base=None) -> CandleBar:
    start = base or datetime(2024, 1, 1, tzinfo=UTC)
    return CandleBar(
        open_time=start + timedelta(hours=i),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("10"),
        is_final=True,
    )


def test_default_fill_model_is_labeled_paper_and_conservative() -> None:
    model = default_fill_model()
    assert model["label"] == PAPER_LABEL
    assert model["fill_policy"] == "next_open"
    assert model["same_candle_ambiguity"] == "conservative_stop_first"


def test_validate_plan_rejects_bad_geometry() -> None:
    model = default_fill_model()
    plan = PaperPlan(
        symbol="BTC/USDT",
        timeframe="1h",
        direction="long",
        signal_bar_open_time=datetime(2024, 1, 1, tzinfo=UTC),
        planned_entry=Decimal("100"),
        stop_price=Decimal("105"),  # invalid for long
        target_price=Decimal("120"),
        invalidation_price=None,
        qty=Decimal("1"),
        risk_amount=Decimal("5"),
        fill_model=model,
    )
    assert "long_stop_not_below_entry" in validate_plan(plan)


def test_fill_only_on_bar_after_signal_never_same_bar() -> None:
    signal = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [_bar(0, o="100"), _bar(1, o="101"), _bar(2, o="102")]
    # Same-bar open must never fill
    same = try_fill_at_next_open(
        signal_bar_open_time=signal,
        direction="long",
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        bars=[bars[0]],
    )
    assert same.filled is False
    filled = try_fill_at_next_open(
        signal_bar_open_time=signal,
        direction="long",
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        bars=bars,
    )
    assert filled.filled is True
    assert filled.entry_bar_open_time == bars[1].open_time
    assert filled.entry_price == Decimal("101")


def test_entry_fill_is_adverse_for_long() -> None:
    signal = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [_bar(1, o="100")]
    filled = try_fill_at_next_open(
        signal_bar_open_time=signal,
        direction="long",
        fill_model=default_fill_model(),
        bars=bars,
    )
    assert filled.filled is True
    assert filled.entry_price is not None and filled.entry_price > Decimal("100")


def test_same_candle_stop_and_target_prefers_stop() -> None:
    entry = datetime(2024, 1, 1, 1, tzinfo=UTC)
    bar = _bar(2, o="100", h="120", low="80", c="110")  # stop 90 and target 115 both hit
    outcome = evaluate_exit_on_bar(
        bar,
        direction="long",
        entry_price=Decimal("100"),
        stop=Decimal("90"),
        target=Decimal("115"),
        invalidation=None,
        entry_bar_open_time=entry,
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        qty=Decimal("1"),
    )
    assert outcome.closed is True
    assert outcome.exit_reason == "stop_target_same_bar_conservative"
    assert outcome.exit_price == Decimal("90")
    assert outcome.realized_r is not None and outcome.realized_r < 0


def test_target_hit_alone_closes_at_target() -> None:
    entry = datetime(2024, 1, 1, 1, tzinfo=UTC)
    bar = _bar(2, o="100", h="130", low="99", c="125")
    outcome = evaluate_exit_on_bar(
        bar,
        direction="long",
        entry_price=Decimal("100"),
        stop=Decimal("90"),
        target=Decimal("120"),
        invalidation=None,
        entry_bar_open_time=entry,
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        qty=Decimal("1"),
    )
    assert outcome.exit_reason == "target"
    assert outcome.exit_price == Decimal("120")
    assert outcome.realized_r == Decimal("2")


def test_invalidation_close_beyond_level() -> None:
    entry = datetime(2024, 1, 1, 1, tzinfo=UTC)
    bar = _bar(2, o="100", h="101", low="94", c="95")  # close below invalidation 96
    outcome = evaluate_exit_on_bar(
        bar,
        direction="long",
        entry_price=Decimal("100"),
        stop=Decimal("90"),
        target=Decimal("120"),
        invalidation=Decimal("96"),
        entry_bar_open_time=entry,
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        qty=Decimal("1"),
    )
    assert outcome.exit_reason == "invalidation"
    assert outcome.exit_price == Decimal("95")


def test_timeout_exits_at_close_after_max_bars() -> None:
    model = default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0", max_bars_in_trade=3)
    bar = _bar(5, o="100", h="101", low="99", c="100.5")
    assert timeout_exit(
        bar,
        direction="long",
        entry_price=Decimal("100"),
        stop=Decimal("90"),
        fill_model=model,
        qty=Decimal("1"),
        bars_held=2,
    ) is None
    timed = timeout_exit(
        bar,
        direction="long",
        entry_price=Decimal("100"),
        stop=Decimal("90"),
        fill_model=model,
        qty=Decimal("1"),
        bars_held=3,
    )
    assert timed is not None
    assert timed.exit_reason == "timeout"
    assert timed.exit_price == Decimal("100.5")


def test_short_same_candle_also_conservative() -> None:
    entry = datetime(2024, 1, 1, 1, tzinfo=UTC)
    bar = _bar(2, o="100", h="110", low="80", c="95")
    outcome = evaluate_exit_on_bar(
        bar,
        direction="short",
        entry_price=Decimal("100"),
        stop=Decimal("108"),
        target=Decimal("85"),
        invalidation=None,
        entry_bar_open_time=entry,
        fill_model=default_fill_model(fee_bps="0", slippage_bps="0", spread_bps="0"),
        qty=Decimal("1"),
    )
    assert outcome.exit_reason == "stop_target_same_bar_conservative"
    assert outcome.exit_price == Decimal("108")
