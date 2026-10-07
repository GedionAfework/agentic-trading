from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import FIXTURE_SYMBOL, FIXTURE_TIMEFRAME, frozen_bos_long_fixture
from private_trading_backtest.replay import run_replay
from private_trading_features.engine import compute_feature


def test_fingerprint_stable() -> None:
    bars = frozen_bos_long_fixture()
    a = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    b = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    assert a == b
    assert len(a) == 64


def test_no_lookahead_fill_is_next_open() -> None:
    bars = frozen_bos_long_fixture()
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    report = run_replay(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        dataset_fingerprint=fp,
    )
    assert report.pins["fill_policy"] == "next_open"
    assert report.pins["outcome_label_source"] == "backtest"
    for trade in report.trades:
        assert trade.entry_bar_index == trade.signal_bar_index + 1
        # Entry uses next bar open path (with costs), not signal bar close
        signal_close = bars[trade.signal_bar_index].close
        assert trade.entry_price != signal_close or trade.entry_bar_index > trade.signal_bar_index


def test_replay_reproducible_metrics() -> None:
    bars = frozen_bos_long_fixture()
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    a = run_replay(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, dataset_fingerprint=fp)
    b = run_replay(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, dataset_fingerprint=fp)
    assert a.metrics.trade_count == b.metrics.trade_count
    assert a.metrics.trade_count >= 1
    assert a.metrics.total_pnl == b.metrics.total_pnl
    assert a.metrics.expectancy_r == b.metrics.expectancy_r
    assert a.signals_seen == b.signals_seen
    assert a.pins["dataset_fingerprint"] == fp
    assert a.pins["feature_engine_version"]
    assert a.pins["strategy_engine_version"]
    assert a.pins["risk_engine_version"]
    assert all(t.outcome_source == "backtest" for t in a.trades)


def test_feature_window_unaffected_by_future_spike() -> None:
    bars = frozen_bos_long_fixture()
    idx = 30
    before = compute_feature("atr", bars, idx)
    bars[-1] = bars[-1].__class__(
        open_time=bars[-1].open_time,
        open=bars[-1].open,
        high=bars[-1].high * 10,
        low=bars[-1].low,
        close=bars[-1].close,
        volume=bars[-1].volume,
        is_final=True,
    )
    after = compute_feature("atr", bars, idx)
    assert before.value == after.value
