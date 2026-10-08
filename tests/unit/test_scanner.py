from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_agents.scanner import (
    dedupe_key,
    evaluate_closed_candle,
    prefilter_passes,
    setup_anchor,
)
from private_trading_backtest.fixtures import (
    FIXTURE_BOS_INDEX,
    FIXTURE_PAD,
    FIXTURE_RETEST_INDEX,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_features.types import CandleBar


def _bars_to(index: int) -> list[CandleBar]:
    return frozen_bos_long_fixture()[: index + 1]


def test_stale_data_never_publishes_even_on_bos_candle() -> None:
    outcome = evaluate_closed_candle(
        _bars_to(FIXTURE_RETEST_INDEX),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        fresh=False,
        actionable=False,
    )
    assert outcome.status == "skipped_stale"
    assert outcome.publishable is False
    assert outcome.dedupe_key is None
    assert outcome.snapshot is None


def test_prefilter_skips_full_pipeline_on_quiet_candle() -> None:
    bars = _bars_to(FIXTURE_PAD - 1)
    assert prefilter_passes(bars, len(bars) - 1) is False
    outcome = evaluate_closed_candle(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, fresh=True, actionable=True
    )
    assert outcome.status == "prefilter_no_setup"
    assert outcome.publishable is False
    assert outcome.snapshot is None


def test_bos_candle_produces_candidate_with_stable_dedupe_key() -> None:
    bars = _bars_to(FIXTURE_BOS_INDEX)
    first = evaluate_closed_candle(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, fresh=True, actionable=True
    )
    second = evaluate_closed_candle(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, fresh=True, actionable=True
    )
    assert first.status == "completed"
    assert first.action == "ENTER"
    assert first.publishable is True
    assert first.dedupe_key == second.dedupe_key
    assert first.dedupe_key.startswith("wyckoff-hdm:v1:BTC/USDT:1h:last_swing_high@")
    assert first.signal_type == "enter_long"


def test_dedupe_key_components() -> None:
    key = dedupe_key(
        strategy_code="wyckoff-hdm",
        strategy_version_no=2,
        symbol="ETH/USDT",
        timeframe="15m",
        setup_anchor="last_swing_high@3000",
        signal_type="enter_long",
    )
    assert key == "wyckoff-hdm:v2:ETH/USDT:15m:last_swing_high@3000:enter_long"


def test_setup_anchor_falls_back_to_bar_time() -> None:
    bars = _bars_to(FIXTURE_BOS_INDEX)
    outcome = evaluate_closed_candle(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, fresh=True, actionable=True
    )
    assert outcome.snapshot is not None
    outcome.snapshot.evidence["features"]["last_swing_high"] = {"status": "unknown", "value": None}
    assert setup_anchor(outcome.snapshot).startswith("bar@")


def test_insufficient_bars_is_skipped_not_failed() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        CandleBar(
            open_time=base + timedelta(hours=i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("10"),
            is_final=True,
        )
        for i in range(5)
    ]
    outcome = evaluate_closed_candle(
        bars, symbol="X", timeframe="1h", fresh=True, actionable=True
    )
    assert outcome.status == "skipped_insufficient_bars"
    assert outcome.publishable is False
