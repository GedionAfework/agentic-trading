from decimal import Decimal

from private_trading_paper_trade.promotion import (
    evaluate_paper_promotion,
    locked_paper_risk_pct,
)


def test_locked_risk_never_exceeds_half_percent_and_cuts_after_rough_dd() -> None:
    assert locked_paper_risk_pct(2.0) == Decimal("0.5")
    assert locked_paper_risk_pct(12.0) == Decimal("0.35")
    assert locked_paper_risk_pct(18.0) == Decimal("0.25")


def test_step4_waits_until_step3_passes() -> None:
    result = evaluate_paper_promotion(
        {
            "approved_for_paper_promotion": False,
            "decision": "WAIT",
            "max_drawdown_r": 8.0,
        }
    )
    assert result["decision"] == "WAIT"
    assert result["live_alerts_allowed"] is False
    assert "WAIT" in result["other_pairs"]
    assert "step3_not_approved" in result["blocking_gates"]


def test_step4_confirms_paper_only_when_step3_passes() -> None:
    result = evaluate_paper_promotion(
        {
            "approved_for_paper_promotion": True,
            "decision": "PASS",
            "max_drawdown_r": 8.0,
        }
    )
    assert result["decision"] == "PASS"
    assert result["soak_confirmed_for_paper"] is True
    assert result["paper_only"] is True
    assert result["live_alerts_allowed"] is False
    assert result["locked_risk_pct"] == "0.5"
    assert result["blocking_gates"] == []
