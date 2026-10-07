from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import FIXTURE_SYMBOL, FIXTURE_TIMEFRAME, frozen_bos_long_fixture
from private_trading_decision.builder import build_training_dataset, serialize_rows_jsonl
from private_trading_decision.matrix import rows_from_jsonl
from private_trading_decision.predict import LoadedModel, apply_gates
from private_trading_decision.train import train_baseline_and_challenger


def _rows():
    bars = frozen_bos_long_fixture()
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    built = build_training_dataset(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source_dataset_fingerprint=fp,
    )
    return built.rows


def test_risk_veto_overrides_high_score() -> None:
    decision = apply_gates(
        score=0.99,
        threshold=0.55,
        strategy_ready=True,
        risk_approved=False,
        mode="champion",
    )
    assert decision.recommendation == "WAIT"
    assert decision.reason == "strategy_or_risk_veto"
    assert decision.gates_passed is False
    assert decision.cannot_bypass_strategy_or_risk is True
    assert decision.llm_may_invent_probability is False
    assert decision.not_a_calibrated_probability is True
    assert "risk_veto" in decision.hard_blockers


def test_shadow_score_does_not_change_gate_decision() -> None:
    decision = apply_gates(
        score=0.01,
        threshold=0.55,
        strategy_ready=True,
        risk_approved=True,
        mode="shadow",
    )
    assert decision.recommendation == "ENTER"
    assert decision.reason == "gates_passed_shadow_score_informational"
    assert decision.band == "abstain"


def test_champion_abstains_below_threshold() -> None:
    decision = apply_gates(
        score=0.2,
        threshold=0.55,
        strategy_ready=True,
        risk_approved=True,
        mode="champion",
    )
    assert decision.recommendation == "WAIT"
    assert decision.reason == "model_abstain"


def test_train_reports_out_of_sample_and_tunes_on_validation() -> None:
    trained = train_baseline_and_challenger(_rows())
    for candidate in (trained.baseline, trained.challenger):
        assert candidate.metrics["selection_split"] == "val"
        assert "test" in candidate.metrics
        assert candidate.metrics["threshold_source"]
        assert any("Test split was not used" in note for note in candidate.metrics["notes"])
        assert candidate.fingerprint
    assert trained.recommended_role in {"baseline", "challenger"}
    assert any("shadow" in note for note in trained.notes)


def test_loaded_artifact_cannot_enter_on_veto() -> None:
    trained = train_baseline_and_challenger(_rows())
    model = LoadedModel(trained.baseline.artifact)
    features = _rows()[0].features
    decision = model.decide(features, strategy_ready=False, risk_approved=True, mode="champion")
    assert decision.recommendation == "WAIT"
    assert decision.gates_passed is False


def test_jsonl_rows_roundtrip_for_training() -> None:
    rows = _rows()
    restored = rows_from_jsonl(serialize_rows_jsonl(rows))
    assert len(restored) == len(rows)
    assert restored[0].label == rows[0].label
    assert restored[0].strategy_version_no == rows[0].strategy_version_no
