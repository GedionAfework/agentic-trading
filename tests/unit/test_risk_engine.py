from decimal import Decimal

from private_trading_risk import (
    Direction,
    InstrumentRiskMeta,
    RiskInput,
    assess_risk,
    default_policy_config,
)


def _ok_input(**overrides) -> RiskInput:
    base = dict(
        direction=Direction.LONG,
        entry=Decimal("100"),
        stop=Decimal("95"),
        target_1=Decimal("110"),
        data_fresh=True,
        market_actionable=True,
        account_equity=Decimal("10000"),
        instrument=InstrumentRiskMeta(
            asset_class="crypto",
            price_tick=Decimal("0.01"),
            qty_step=Decimal("0.001"),
            min_notional=Decimal("10"),
        ),
    )
    base.update(overrides)
    return RiskInput(**base)


def test_approved_valid_long_setup() -> None:
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=_ok_input(),
    )
    assert result.approved is True
    assert result.rr_ratio == Decimal("2")
    assert result.hard_blockers == []
    assert result.meta["never_places_live_orders"] is True
    assert result.paper_size is not None
    assert result.paper_size.quantity is not None


def test_entry_equals_stop_blocked() -> None:
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=_ok_input(stop=Decimal("100")),
    )
    assert result.approved is False
    assert "entry_equals_stop" in result.hard_blockers


def test_rr_below_minimum_blocked() -> None:
    # risk 5, reward 5 → rr=1.0 < 2.0
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=_ok_input(target_1=Decimal("105")),
    )
    assert result.approved is False
    assert any(b.startswith("rr_below_minimum") for b in result.hard_blockers)


def test_stale_data_fail_closed() -> None:
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=_ok_input(data_fresh=False),
    )
    assert result.approved is False
    assert "stale_market_data" in result.hard_blockers


def test_forbidden_certainty_language_blocked() -> None:
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(),
        risk_input=_ok_input(summary_text="This is a guaranteed profit setup"),
    )
    assert result.approved is False
    assert "forbidden_certainty_language" in result.hard_blockers


def test_weekend_warn_does_not_block() -> None:
    result = assess_risk(
        policy_code="default-crypto",
        policy_version_no=1,
        policy_config=default_policy_config(weekend_policy="warn"),
        risk_input=_ok_input(is_weekend=True),
    )
    assert result.approved is True
    assert "weekend_policy_warning" in result.warnings
