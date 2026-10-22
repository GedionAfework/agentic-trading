from private_trading_paper_trade.live_alert_gate import evaluate_live_alert_decision


def test_step5_defaults_to_wait_and_never_enables_alerts() -> None:
    result = evaluate_live_alert_decision(
        {
            "soak_confirmed_for_paper": False,
            "decision": "WAIT",
            "locked_risk_pct": "0.5",
            "observed_max_drawdown_r": 8.0,
        },
        owner_unlock=False,
    )
    assert result["decision"] == "WAIT"
    assert result["live_alerts_allowed"] is False
    assert result["channel"] == "telegram"
    assert "step4_not_confirmed" in result["blocking_gates"]
    assert "owner_unlock_required" in result["blocking_gates"]


def test_step5_ready_still_leaves_live_alerts_disabled() -> None:
    result = evaluate_live_alert_decision(
        {
            "soak_confirmed_for_paper": True,
            "decision": "PASS",
            "locked_risk_pct": "0.35",
            "observed_max_drawdown_r": 12.0,
        },
        owner_unlock=True,
    )
    assert result["decision"] == "READY"
    assert result["eligible_for_release_enable"] is True
    assert result["live_alerts_allowed"] is False
    assert result["paper_only"] is True
    assert result["locked_risk_pct"] == "0.35"
    assert result["blocking_gates"] == []
