from __future__ import annotations

from datetime import UTC, datetime

from private_trading_release.execution import execution_status
from private_trading_release.policy import (
    ReleasePolicy,
    evaluate_alert_gate,
    in_quiet_hours,
)


def test_quiet_hours_wrap_midnight() -> None:
    assert in_quiet_hours(
        datetime(2026, 10, 8, 23, tzinfo=UTC), start=22, end=6
    )
    assert in_quiet_hours(datetime(2026, 10, 8, 3, tzinfo=UTC), start=22, end=6)
    assert not in_quiet_hours(
        datetime(2026, 10, 8, 12, tzinfo=UTC), start=22, end=6
    )


def test_lab_mode_allows_when_live_disabled() -> None:
    policy = ReleasePolicy(live_alerts_enabled=False)
    result = evaluate_alert_gate(
        policy=policy,
        symbol="DOGE/USDT",
        timeframe="5m",
        action="ENTER",
        confidence_band="low",
        risk_approved=False,
        now=datetime(2026, 10, 8, 12, tzinfo=UTC),
        notifications_enabled=True,
        checklist_complete=False,
        soak_complete=False,
        integrity_ok=False,
        active_waiver_codes=set(),
    )
    assert result["allow"] is True
    assert result["mode"] == "lab"


def test_kill_switch_blocks() -> None:
    result = evaluate_alert_gate(
        policy=ReleasePolicy(live_alerts_enabled=True),
        symbol="BTC/USDT",
        timeframe="1h",
        action="ENTER",
        confidence_band="high",
        risk_approved=True,
        now=datetime(2026, 10, 8, 12, tzinfo=UTC),
        notifications_enabled=False,
        checklist_complete=True,
        soak_complete=True,
        integrity_ok=True,
        active_waiver_codes=set(),
    )
    assert result["allow"] is False
    assert result["publish_state"] == "suppressed_kill_switch"


def test_production_narrow_scope() -> None:
    policy = ReleasePolicy(live_alerts_enabled=True)
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    blocked = evaluate_alert_gate(
        policy=policy,
        symbol="SOL/USDT",
        timeframe="1h",
        action="ENTER",
        confidence_band="high",
        risk_approved=True,
        now=now,
        notifications_enabled=True,
        checklist_complete=True,
        soak_complete=True,
        integrity_ok=True,
        active_waiver_codes=set(),
    )
    assert blocked["allow"] is False
    assert "symbol_not_approved:SOL/USDT" in blocked["reasons"]

    ok = evaluate_alert_gate(
        policy=policy,
        symbol="BTC/USDT",
        timeframe="1h",
        action="ENTER",
        confidence_band="medium",
        risk_approved=True,
        now=now,
        notifications_enabled=True,
        checklist_complete=True,
        soak_complete=True,
        integrity_ok=True,
        active_waiver_codes=set(),
    )
    assert ok["allow"] is True
    assert ok["mode"] == "production"


def test_soak_waiver_allows_production() -> None:
    policy = ReleasePolicy(live_alerts_enabled=True)
    result = evaluate_alert_gate(
        policy=policy,
        symbol="BTC/USDT",
        timeframe="1h",
        action="ENTER",
        confidence_band="high",
        risk_approved=True,
        now=datetime(2026, 10, 8, 12, tzinfo=UTC),
        notifications_enabled=True,
        checklist_complete=True,
        soak_complete=False,
        integrity_ok=True,
        active_waiver_codes={"gate_f_soak_incomplete"},
    )
    assert result["allow"] is True


def test_execution_undeployed() -> None:
    status = execution_status()
    assert status["broker_execution"] == "disabled"
    assert status["ok"] is True
    assert status["execution_package_present"] is False
