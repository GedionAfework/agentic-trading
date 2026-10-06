from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from private_trading_strategies.dsl import evaluate_expression
from private_trading_strategies.types import (
    Direction,
    FeatureFact,
    RuleEvaluation,
    RuleResult,
    SetupState,
    StrategyAssessment,
)

STRATEGY_ENGINE_VERSION = "0.1.0"


@dataclass(slots=True, frozen=True)
class RuleDef:
    code: str
    name: str
    rule_type: str
    expression: dict[str, Any]
    required: bool = True
    weight: float = 0.0
    sort_order: int = 0
    gate_group: str = "hard"


@dataclass(slots=True, frozen=True)
class StrategyDefinition:
    code: str
    version_no: int
    direction_mode: str
    rules: tuple[RuleDef, ...]
    config: dict[str, Any]
    engine_version: str = STRATEGY_ENGINE_VERSION


def _feature_map(raw: dict[str, Any]) -> dict[str, FeatureFact]:
    out: dict[str, FeatureFact] = {}
    for name, payload in raw.items():
        if isinstance(payload, FeatureFact):
            out[name] = payload
            continue
        if isinstance(payload, dict):
            status = RuleResult(str(payload.get("status", "unknown")))
            out[name] = FeatureFact(
                status=status,
                value=payload.get("value"),
                reason=payload.get("reason"),
            )
            continue
        # bare bool / scalar → known TRUE with that value
        if isinstance(payload, bool):
            out[name] = FeatureFact(
                status=RuleResult.TRUE if payload else RuleResult.FALSE,
                value=payload,
            )
        else:
            out[name] = FeatureFact(status=RuleResult.TRUE, value=payload)
    return out


def evaluate_strategy(
    definition: StrategyDefinition,
    *,
    direction: Direction | str,
    features: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> StrategyAssessment:
    direction_s = Direction(str(direction))
    if definition.direction_mode not in {"both", direction_s.value}:
        return StrategyAssessment(
            strategy_code=definition.code,
            strategy_version_no=definition.version_no,
            engine_version=definition.engine_version,
            direction=direction_s,
            setup_state=SetupState.NO_SETUP,
            rule_evaluations=[],
            blockers=["direction_not_allowed"],
        )

    ctx = dict(context or {})
    # Allow advisory override of unlocked definitions via config
    advisory_defs = set(definition.config.get("advisory_definitions", []))
    feature_facts = _feature_map(features)

    evaluations: list[RuleEvaluation] = []
    for rule in sorted(definition.rules, key=lambda r: r.sort_order):
        expr = rule.expression
        # Rewrite definition_unlocked → advisory_true when configured
        if (
            expr.get("op") == "definition_unlocked"
            and expr.get("definition_id") in advisory_defs
        ):
            expr = {
                "op": "advisory_true",
                "definition_id": expr.get("definition_id"),
            }
        result, reason, evidence = evaluate_expression(
            expr,
            features=feature_facts,
            context=ctx,
            direction=direction_s.value,
        )
        evaluations.append(
            RuleEvaluation(
                code=rule.code,
                name=rule.name,
                result=result,
                required=rule.required,
                gate_group=rule.gate_group,
                reason=reason,
                evidence=evidence,
            )
        )

    blockers: list[str] = []
    warnings: list[str] = []
    required_failed = False
    required_unknown = False
    for ev in evaluations:
        if not ev.required:
            if ev.result != RuleResult.TRUE:
                warnings.append(f"{ev.code}:{ev.result}")
            continue
        if ev.result == RuleResult.FALSE:
            required_failed = True
            blockers.append(f"{ev.code}:FALSE:{ev.reason or 'failed'}")
        elif ev.result == RuleResult.UNKNOWN:
            required_unknown = True
            blockers.append(f"{ev.code}:UNKNOWN:{ev.reason or 'unknown'}")

    entry_path = str(ctx.get("entry_path", "aggressive"))
    retest_complete = bool(ctx.get("retest_complete", False))

    if required_failed:
        # Hard false on structure/volume → no setup; soft false on five-question → wait
        hard_false = any(
            ev.required
            and ev.result == RuleResult.FALSE
            and ev.gate_group == "hard"
            for ev in evaluations
        )
        setup_state = SetupState.NO_SETUP if hard_false else SetupState.WAIT
    elif required_unknown:
        setup_state = SetupState.WAIT
    else:
        # All required TRUE
        if entry_path == "safer" and not retest_complete:
            setup_state = SetupState.WAIT_FOR_CONFIRMATION
        else:
            setup_state = SetupState.READY_FOR_REVIEW

    # Optional score: sum weights of required TRUE rules
    score = 0.0
    weight_total = 0.0
    rule_by_code = {r.code: r for r in definition.rules}
    for ev in evaluations:
        rule = rule_by_code[ev.code]
        if rule.weight <= 0:
            continue
        weight_total += float(rule.weight)
        if ev.result == RuleResult.TRUE:
            score += float(rule.weight)
    score_out = (score / weight_total) if weight_total > 0 else None

    return StrategyAssessment(
        strategy_code=definition.code,
        strategy_version_no=definition.version_no,
        engine_version=definition.engine_version,
        direction=direction_s,
        setup_state=setup_state,
        rule_evaluations=evaluations,
        blockers=blockers,
        warnings=warnings,
        score=score_out,
        meta={
            "entry_path": entry_path,
            "retest_complete": retest_complete,
            "advisory_definitions": sorted(advisory_defs),
        },
    )
