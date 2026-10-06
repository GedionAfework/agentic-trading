from __future__ import annotations

from private_trading_strategies import (
    Direction,
    SetupState,
    build_wyckoff_hdm_v1,
    evaluate_strategy,
)


def _ready_features() -> dict:
    return {
        "bos_bullish": {"status": "true", "value": True},
        "bos_bearish": {"status": "false", "value": False},
        "significant_volume": {"status": "true", "value": True},
        "low_volume": {"status": "true", "value": True},
    }


def _ready_context() -> dict:
    return {
        "htf_bias": "long",
        "structural_stop_ok": True,
        "rr_to_tp1": 2.5,
        "entry_path": "aggressive",
    }


def test_at011_ready_when_advisory_unlocked() -> None:
    definition = build_wyckoff_hdm_v1(
        advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    assessment = evaluate_strategy(
        definition,
        direction=Direction.LONG,
        features=_ready_features(),
        context=_ready_context(),
    )
    assert assessment.setup_state == SetupState.READY_FOR_REVIEW
    assert assessment.ready is True


def test_at012_bos_false_never_ready() -> None:
    definition = build_wyckoff_hdm_v1(
        advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    features = _ready_features()
    features["bos_bullish"] = {"status": "false", "value": False}
    assessment = evaluate_strategy(
        definition,
        direction=Direction.LONG,
        features=features,
        context=_ready_context(),
    )
    assert assessment.setup_state == SetupState.NO_SETUP
    assert assessment.ready is False
    assert any(b.startswith("bos_confirmed:FALSE") for b in assessment.blockers)


def test_at013_missing_rr_is_wait() -> None:
    definition = build_wyckoff_hdm_v1(
        advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    ctx = _ready_context()
    del ctx["rr_to_tp1"]
    assessment = evaluate_strategy(
        definition,
        direction=Direction.LONG,
        features=_ready_features(),
        context=ctx,
    )
    assert assessment.setup_state == SetupState.WAIT
    assert assessment.ready is False
    q_min = next(e for e in assessment.rule_evaluations if e.code == "q_min_rr")
    assert q_min.result.value == "unknown"


def test_unlocked_definitions_block_ready_by_default() -> None:
    definition = build_wyckoff_hdm_v1(advisory_definitions=[])
    assessment = evaluate_strategy(
        definition,
        direction=Direction.LONG,
        features=_ready_features(),
        context=_ready_context(),
    )
    assert assessment.ready is False
    assert assessment.setup_state == SetupState.WAIT
    assert any("DEFINITION_UNLOCKED" in b for b in assessment.blockers)


def test_safer_path_waits_for_retest() -> None:
    definition = build_wyckoff_hdm_v1(
        advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    ctx = _ready_context()
    ctx["entry_path"] = "safer"
    ctx["retest_complete"] = False
    assessment = evaluate_strategy(
        definition,
        direction=Direction.LONG,
        features=_ready_features(),
        context=ctx,
    )
    assert assessment.setup_state == SetupState.WAIT_FOR_CONFIRMATION
    assert assessment.ready is False
