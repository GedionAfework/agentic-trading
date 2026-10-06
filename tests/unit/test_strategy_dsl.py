from private_trading_strategies.dsl import evaluate_expression
from private_trading_strategies.types import FeatureFact, RuleResult


def test_all_short_circuits_on_false() -> None:
    result, reason, _ = evaluate_expression(
        {
            "op": "all",
            "args": [
                {"op": "literal", "value": "true"},
                {"op": "literal", "value": "false"},
                {"op": "literal", "value": "true"},
            ],
        },
        features={},
        context={},
        direction="long",
    )
    assert result == RuleResult.FALSE


def test_feature_missing_is_unknown() -> None:
    result, reason, evidence = evaluate_expression(
        {"op": "feature_status", "feature": "bos_bullish", "equals": "true"},
        features={},
        context={},
        direction="long",
    )
    assert result == RuleResult.UNKNOWN
    assert reason == "missing_feature"
    assert evidence["feature"] == "bos_bullish"


def test_switch_direction() -> None:
    features = {
        "bos_bullish": FeatureFact(status=RuleResult.TRUE, value=True),
        "bos_bearish": FeatureFact(status=RuleResult.FALSE, value=False),
    }
    long_r, _, _ = evaluate_expression(
        {
            "op": "switch_direction",
            "long": {"op": "feature_status", "feature": "bos_bullish", "equals": "true"},
            "short": {"op": "feature_status", "feature": "bos_bearish", "equals": "true"},
        },
        features=features,
        context={},
        direction="long",
    )
    assert long_r == RuleResult.TRUE
