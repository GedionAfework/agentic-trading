"""Agentic shadow soak: primary deterministic, shadow never overrides."""

from __future__ import annotations

from dataclasses import replace

import pytest
from private_trading_agents.scanner import evaluate_closed_candle
from private_trading_agents.shadow import (
    attach_shadow_evidence,
    compare_decision_snapshots,
    run_decision_with_optional_shadow,
)
from private_trading_agents.workflow import DecisionAction, run_decision_workflow
from private_trading_backtest.fixtures import (
    FIXTURE_BOS_INDEX,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)


def _bars():
    return frozen_bos_long_fixture()


def test_shadow_off_by_default_no_evidence_block() -> None:
    snap = run_decision_with_optional_shadow(
        _bars(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=19,
        shadow=False,
    )
    assert snap.action == DecisionAction.NO_SETUP
    assert "agentic_shadow" not in snap.evidence


def test_shadow_on_parity_with_deterministic() -> None:
    bars = _bars()
    for bar_index in (19, FIXTURE_BOS_INDEX):
        snap = run_decision_with_optional_shadow(
            bars,
            symbol=FIXTURE_SYMBOL,
            timeframe=FIXTURE_TIMEFRAME,
            bar_index=bar_index,
            shadow=True,
        )
        shadow = snap.evidence["agentic_shadow"]
        assert shadow["overrides_primary"] is False
        assert shadow["parity"] is True
        assert shadow["mismatched_fields"] == []
        assert shadow["primary_action"] == snap.action.value
        assert shadow["shadow_action"] == snap.action.value
        assert snap.evidence["orchestrator_mode"] == "deterministic"


def test_shadow_mismatch_does_not_override_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    import private_trading_agents.shadow as shadow_mod

    bars = _bars()
    real_primary = run_decision_workflow(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=FIXTURE_BOS_INDEX,
        mode="deterministic",
    )
    assert real_primary.action == DecisionAction.ENTER
    fake_shadow = replace(real_primary, action=DecisionAction.WAIT)
    real_run = shadow_mod.run_decision_workflow

    def _fake_run(bars_arg, *, mode="deterministic", **kwargs):  # noqa: ANN001
        if mode == "agentic":
            return fake_shadow
        return real_run(bars_arg, mode="deterministic", **kwargs)

    monkeypatch.setattr(shadow_mod, "run_decision_workflow", _fake_run)

    out = run_decision_with_optional_shadow(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=FIXTURE_BOS_INDEX,
        shadow=True,
    )
    assert out.action == DecisionAction.ENTER  # primary wins
    assert out.evidence["agentic_shadow"]["parity"] is False
    assert "action" in out.evidence["agentic_shadow"]["mismatched_fields"]
    assert out.evidence["agentic_shadow"]["shadow_action"] == "WAIT"
    assert out.evidence["agentic_shadow"]["overrides_primary"] is False


def test_shadow_error_is_recorded_primary_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    import private_trading_agents.shadow as shadow_mod

    real_run = shadow_mod.run_decision_workflow

    def _boom(bars_arg, *, mode="deterministic", **kwargs):  # noqa: ANN001
        if mode == "agentic":
            raise RuntimeError("shadow exploded")
        return real_run(bars_arg, mode="deterministic", **kwargs)

    monkeypatch.setattr(shadow_mod, "run_decision_workflow", _boom)
    out = run_decision_with_optional_shadow(
        _bars(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=19,
        shadow=True,
    )
    assert out.action == DecisionAction.NO_SETUP
    assert out.evidence["agentic_shadow"]["parity"] is False
    assert "shadow exploded" in (out.evidence["agentic_shadow"]["shadow_error"] or "")


def test_compare_helper_detects_blocker_drift() -> None:
    bars = _bars()
    a = run_decision_workflow(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, bar_index=19
    )
    b = replace(a, hard_blockers=["injected"])
    result = compare_decision_snapshots(a, b)
    assert result.parity is False
    assert "hard_blockers" in result.mismatched_fields
    attached = attach_shadow_evidence(a, result)
    assert attached.action == a.action
    assert attached.evidence["agentic_shadow"]["parity"] is False


def test_scanner_path_still_deterministic_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    import private_trading_agents.shadow as shadow_mod

    monkeypatch.setattr(shadow_mod, "shadow_agentic_enabled", lambda explicit=None: True)
    bars = _bars()
    # Truncate so last bar is the BOS index candle when possible.
    sliced = bars[: FIXTURE_BOS_INDEX + 1]
    if len(sliced) < 50:
        pytest.skip("fixture shorter than scanner MIN_BARS")
    outcome = evaluate_closed_candle(
        sliced,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        fresh=True,
        actionable=True,
    )
    if outcome.snapshot is None:
        # prefilter may skip if last bar is not BOS
        return
    assert outcome.snapshot.evidence.get("orchestrator_mode") == "deterministic"
    assert outcome.snapshot.evidence["agentic_shadow"]["overrides_primary"] is False
    assert outcome.snapshot.evidence["agentic_shadow"]["parity"] is True
