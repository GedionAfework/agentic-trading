from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import FIXTURE_SYMBOL, FIXTURE_TIMEFRAME, frozen_bos_long_fixture
from private_trading_decision.builder import build_training_dataset, serialize_rows_jsonl
from private_trading_decision.labels import FEATURE_NAMES, label_bar
from private_trading_decision.splits import (
    TimeSplitConfig,
    assign_time_splits,
    assert_no_time_leakage,
)
from private_trading_decision.types import LabelClass, LabelPolicy, TrainingRow
from private_trading_features.engine import compute_feature


def _source_fp() -> tuple[list, str]:
    bars = frozen_bos_long_fixture()
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    return bars, fp


def test_build_includes_non_winners_and_traceability() -> None:
    bars, fp = _source_fp()
    result = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
    )
    assert len(result.rows) >= 1
    labels = {r.label for r in result.rows}
    assert LabelClass.WAIT in labels or LabelClass.NO_SETUP in labels or LabelClass.LOSS in labels
    assert result.quality_report["includes_non_winners"] is True
    trace = result.quality_report["traceability"]
    assert trace["all_rows_have_source_timestamp"] is True
    assert trace["all_rows_have_strategy_version"] is True
    assert trace["all_rows_have_label_policy"] is True
    assert result.source_dataset_fingerprint == fp
    assert set(result.feature_schema) == set(FEATURE_NAMES)
    assert result.engine_versions["dataset_builder_version"]
    assert result.engine_versions["feature_engine_version"]
    assert result.split_manifest["mode"] == "time"


def test_fingerprint_stable_and_jsonl_roundtrip() -> None:
    bars, fp = _source_fp()
    a = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
    )
    b = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
    )
    assert a.fingerprint == b.fingerprint
    assert len(a.fingerprint) == 64
    payload = serialize_rows_jsonl(a.rows)
    assert payload.count(b"\n") == len(a.rows)
    assert b'"label_policy_id"' in payload


def test_time_splits_no_leakage() -> None:
    bars, fp = _source_fp()
    result = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
        split_mode="time",
    )
    assert_no_time_leakage(result.rows)
    train = [r for r in result.rows if r.split == "train"]
    test = [r for r in result.rows if r.split == "test"]
    if train and test:
        assert max(r.open_time for r in train) < min(r.open_time for r in test)


def test_walk_forward_manifest() -> None:
    bars, fp = _source_fp()
    result = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
        split_mode="walk_forward",
    )
    assert result.split_manifest["mode"] == "walk_forward"
    assert len(result.split_manifest["folds"]) >= 1
    assert_no_time_leakage(result.rows)


def test_label_bar_features_ignore_future_spike() -> None:
    bars, _fp = _source_fp()
    idx = 30
    policy = LabelPolicy()
    before = label_bar(bars, idx, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, policy=policy)
    atr_before = compute_feature("atr", bars, idx)
    bars[-1] = bars[-1].__class__(
        open_time=bars[-1].open_time,
        open=bars[-1].open,
        high=bars[-1].high * 10,
        low=bars[-1].low,
        close=bars[-1].close,
        volume=bars[-1].volume,
        is_final=True,
    )
    after = label_bar(bars, idx, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, policy=policy)
    atr_after = compute_feature("atr", bars, idx)
    assert atr_before.value == atr_after.value
    assert before.features["atr"]["value"] == after.features["atr"]["value"]
    assert before.label_policy_id == "label.v1"
    assert before.strategy_code == "wyckoff-hdm"


def test_assign_time_splits_ratios() -> None:
    from datetime import UTC, datetime, timedelta

    rows = []
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(10):
        rows.append(
            TrainingRow(
                row_id=str(i),
                bar_index=i,
                open_time=base + timedelta(hours=i),
                symbol="X",
                timeframe="1h",
                features={},
                feature_versions={},
                setup_state="wait",
                direction="long",
                label=LabelClass.WAIT,
                pnl_r=None,
                exit_reason=None,
                entry_bar_index=None,
                exit_bar_index=None,
                strategy_code="wyckoff-hdm",
                strategy_version_no=1,
                label_policy_id="label.v1",
                label_policy_version="1.0.0",
                outcome_source="backtest",
                source_bar_open_time=base + timedelta(hours=i),
            )
        )
    ordered, manifest = assign_time_splits(rows, config=TimeSplitConfig())
    assert sum(manifest["counts"].values()) == 10
    assert_no_time_leakage(ordered)
