from __future__ import annotations

from private_trading_strategies.evaluate import RuleDef, StrategyDefinition, STRATEGY_ENGINE_VERSION

MIN_RR = 2.0


def build_wyckoff_hdm_v1(
    *,
    version_no: int = 1,
    advisory_definitions: list[str] | None = None,
) -> StrategyDefinition:
    """Crypto-first Spec v1 gates. Unlocked definitions fail closed unless advisory."""
    rules = (
        RuleDef(
            code="htf_aligned",
            name="HTF bias agrees with trade direction",
            rule_type="comparison",
            expression={
                "op": "context_eq",
                "key": "htf_bias",
                "equals": {"op": "passthrough"},  # replaced below
            },
            required=True,
            weight=1,
            sort_order=10,
            gate_group="hard",
        ),
        RuleDef(
            code="bos_confirmed",
            name="BOS confirmed in trade direction",
            rule_type="composite",
            expression={
                "op": "switch_direction",
                "long": {"op": "feature_status", "feature": "bos_bullish", "equals": "true"},
                "short": {"op": "feature_status", "feature": "bos_bearish", "equals": "true"},
            },
            required=True,
            weight=2,
            sort_order=20,
            gate_group="hard",
        ),
        RuleDef(
            code="volume_harmony",
            name="Significant volume supports BOS (VOL-001 EC proxy)",
            rule_type="comparison",
            expression={"op": "feature_bool", "feature": "significant_volume", "equals": True},
            required=True,
            weight=1.5,
            sort_order=30,
            gate_group="hard",
        ),
        RuleDef(
            code="acc_dist_context",
            name="Accumulation/distribution context (WYK-001)",
            rule_type="definition",
            expression={"op": "definition_unlocked", "definition_id": "WYK-001"},
            required=True,
            weight=0,
            sort_order=40,
            gate_group="hard",
        ),
        RuleDef(
            code="imbalance_favoring",
            name="Imbalance favoring direction (ADV until locked)",
            rule_type="definition",
            expression={"op": "definition_unlocked", "definition_id": "IMB-001"},
            required=True,
            weight=0,
            sort_order=50,
            gate_group="hard",
        ),
        RuleDef(
            code="q_bos_volume",
            name="Q1: Confirmed BOS + significant volume",
            rule_type="composite",
            expression={
                "op": "all",
                "args": [
                    {
                        "op": "switch_direction",
                        "long": {
                            "op": "feature_status",
                            "feature": "bos_bullish",
                            "equals": "true",
                        },
                        "short": {
                            "op": "feature_status",
                            "feature": "bos_bearish",
                            "equals": "true",
                        },
                    },
                    {"op": "feature_bool", "feature": "significant_volume", "equals": True},
                ],
            },
            required=True,
            weight=1,
            sort_order=60,
            gate_group="five_question",
        ),
        RuleDef(
            code="q_volume_harmony",
            name="Q2: Harmonious volume",
            rule_type="comparison",
            expression={"op": "feature_bool", "feature": "significant_volume", "equals": True},
            required=True,
            weight=1,
            sort_order=70,
            gate_group="five_question",
        ),
        RuleDef(
            code="q_smart_money",
            name="Q3: Smart Money state (SMT-001)",
            rule_type="definition",
            expression={"op": "definition_unlocked", "definition_id": "SMT-001"},
            required=True,
            weight=0,
            sort_order=80,
            gate_group="five_question",
        ),
        RuleDef(
            code="q_structural_stop",
            name="Q4: Structural stop present",
            rule_type="comparison",
            expression={"op": "context_eq", "key": "structural_stop_ok", "equals": True},
            required=True,
            weight=1,
            sort_order=90,
            gate_group="five_question",
        ),
        RuleDef(
            code="q_min_rr",
            name="Q5: Minimum R:R",
            rule_type="comparison",
            expression={"op": "context_gte", "key": "rr_to_tp1", "value": MIN_RR},
            required=True,
            weight=1,
            sort_order=100,
            gate_group="five_question",
        ),
        RuleDef(
            code="safer_entry_sequence",
            name="Safer entry sequence (ENT-001 EC partial)",
            rule_type="sequence",
            expression={
                "op": "sequence",
                "args": [
                    {
                        "op": "all",
                        "args": [
                            {
                                "op": "switch_direction",
                                "long": {
                                    "op": "feature_status",
                                    "feature": "bos_bullish",
                                    "equals": "true",
                                },
                                "short": {
                                    "op": "feature_status",
                                    "feature": "bos_bearish",
                                    "equals": "true",
                                },
                            },
                            {
                                "op": "feature_bool",
                                "feature": "significant_volume",
                                "equals": True,
                            },
                        ],
                    },
                    {"op": "context_eq", "key": "retest_complete", "equals": True},
                    {"op": "feature_bool", "feature": "low_volume", "equals": True},
                ],
            },
            required=False,
            weight=0.5,
            sort_order=110,
            gate_group="entry_path",
        ),
    )

    # Fix htf_aligned to use switch so equals matches direction
    fixed_rules: list[RuleDef] = []
    for rule in rules:
        if rule.code == "htf_aligned":
            fixed_rules.append(
                RuleDef(
                    code=rule.code,
                    name=rule.name,
                    rule_type=rule.rule_type,
                    expression={
                        "op": "switch_direction",
                        "long": {"op": "context_eq", "key": "htf_bias", "equals": "long"},
                        "short": {"op": "context_eq", "key": "htf_bias", "equals": "short"},
                    },
                    required=rule.required,
                    weight=rule.weight,
                    sort_order=rule.sort_order,
                    gate_group=rule.gate_group,
                )
            )
        else:
            fixed_rules.append(rule)

    return StrategyDefinition(
        code="wyckoff-hdm",
        version_no=version_no,
        direction_mode="both",
        rules=tuple(fixed_rules),
        config={
            "min_rr": MIN_RR,
            "spec_version": "1.0.0-draft",
            "advisory_definitions": list(
                advisory_definitions
                or []
            ),
            "asset_class": "crypto",
        },
        engine_version=STRATEGY_ENGINE_VERSION,
    )
