from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_strategies.types import FeatureFact, RuleResult


def _as_result(raw: str | RuleResult) -> RuleResult:
    return RuleResult(str(raw))


def _fact(features: dict[str, FeatureFact], name: str) -> FeatureFact | None:
    return features.get(name)


def evaluate_expression(
    expression: dict[str, Any],
    *,
    features: dict[str, FeatureFact],
    context: dict[str, Any],
    direction: str,
) -> tuple[RuleResult, str | None, dict[str, Any]]:
    """Constrained DSL → (result, reason, evidence). Missing evidence → UNKNOWN."""
    op = expression.get("op")
    if not op:
        return RuleResult.UNKNOWN, "missing_op", {}

    if op == "literal":
        return _as_result(expression["value"]), None, {"literal": expression["value"]}

    if op == "definition_unlocked":
        def_id = expression.get("definition_id", "UNKNOWN")
        return (
            RuleResult.UNKNOWN,
            "DEFINITION_UNLOCKED",
            {"definition_id": def_id},
        )

    if op == "advisory_true":
        # Soft advisory: TRUE for observability but must not be required alone.
        return (
            RuleResult.TRUE,
            "advisory_only",
            {"definition_id": expression.get("definition_id"), "advisory": True},
        )

    if op == "feature_status":
        name = expression["feature"]
        expected = _as_result(expression.get("equals", "true"))
        fact = _fact(features, name)
        if fact is None:
            return RuleResult.UNKNOWN, "missing_feature", {"feature": name}
        if fact.status == RuleResult.UNKNOWN:
            return RuleResult.UNKNOWN, fact.reason or "feature_unknown", {"feature": name}
        ok = fact.status == expected
        return (
            RuleResult.TRUE if ok else RuleResult.FALSE,
            None if ok else "status_mismatch",
            {"feature": name, "actual": fact.status, "expected": expected, "value": fact.value},
        )

    if op == "feature_bool":
        name = expression["feature"]
        expected = bool(expression.get("equals", True))
        fact = _fact(features, name)
        if fact is None:
            return RuleResult.UNKNOWN, "missing_feature", {"feature": name}
        if fact.status == RuleResult.UNKNOWN:
            return RuleResult.UNKNOWN, fact.reason or "feature_unknown", {"feature": name}
        if fact.status != RuleResult.TRUE:
            # Feature evaluated FALSE means bool is known false when value is False;
            # if status FALSE with value False → compare; if status FALSE for other reasons treat as false.
            actual = bool(fact.value) if fact.value is not None else False
        else:
            actual = bool(fact.value)
        ok = actual is expected
        return (
            RuleResult.TRUE if ok else RuleResult.FALSE,
            None if ok else "bool_mismatch",
            {"feature": name, "actual": actual, "expected": expected},
        )

    if op == "context_eq":
        key = expression["key"]
        if key not in context:
            return RuleResult.UNKNOWN, "missing_context", {"key": key}
        expected = expression.get("equals")
        actual = context[key]
        ok = actual == expected
        return (
            RuleResult.TRUE if ok else RuleResult.FALSE,
            None if ok else "context_mismatch",
            {"key": key, "actual": actual, "expected": expected},
        )

    if op == "context_gte":
        key = expression["key"]
        if key not in context or context[key] is None:
            return RuleResult.UNKNOWN, "missing_context", {"key": key}
        try:
            actual = Decimal(str(context[key]))
            threshold = Decimal(str(expression["value"]))
        except Exception:  # noqa: BLE001
            return RuleResult.UNKNOWN, "invalid_numeric_context", {"key": key}
        ok = actual >= threshold
        return (
            RuleResult.TRUE if ok else RuleResult.FALSE,
            None if ok else "below_threshold",
            {"key": key, "actual": str(actual), "threshold": str(threshold)},
        )

    if op == "switch_direction":
        branch = expression.get(direction)
        if branch is None:
            return RuleResult.UNKNOWN, "missing_direction_branch", {"direction": direction}
        return evaluate_expression(branch, features=features, context=context, direction=direction)

    if op == "all":
        evidence: dict[str, Any] = {"args": []}
        for i, arg in enumerate(expression.get("args", [])):
            result, reason, ev = evaluate_expression(
                arg, features=features, context=context, direction=direction
            )
            evidence["args"].append({"i": i, "result": result, "reason": reason, "evidence": ev})
            if result == RuleResult.UNKNOWN:
                return RuleResult.UNKNOWN, reason, evidence
            if result == RuleResult.FALSE:
                return RuleResult.FALSE, reason, evidence
        if not expression.get("args"):
            return RuleResult.UNKNOWN, "empty_all", evidence
        return RuleResult.TRUE, None, evidence

    if op == "any":
        evidence = {"args": []}
        saw_unknown = False
        unknown_reason: str | None = None
        for i, arg in enumerate(expression.get("args", [])):
            result, reason, ev = evaluate_expression(
                arg, features=features, context=context, direction=direction
            )
            evidence["args"].append({"i": i, "result": result, "reason": reason, "evidence": ev})
            if result == RuleResult.TRUE:
                return RuleResult.TRUE, None, evidence
            if result == RuleResult.UNKNOWN:
                saw_unknown = True
                unknown_reason = reason
        if saw_unknown:
            return RuleResult.UNKNOWN, unknown_reason, evidence
        if not expression.get("args"):
            return RuleResult.UNKNOWN, "empty_any", evidence
        return RuleResult.FALSE, "no_branch_true", evidence

    if op == "not":
        arg = expression.get("arg")
        if not isinstance(arg, dict):
            return RuleResult.UNKNOWN, "invalid_not", {}
        result, reason, ev = evaluate_expression(
            arg, features=features, context=context, direction=direction
        )
        if result == RuleResult.UNKNOWN:
            return RuleResult.UNKNOWN, reason, ev
        flipped = RuleResult.FALSE if result == RuleResult.TRUE else RuleResult.TRUE
        return flipped, None, {"inner": ev, "inner_result": result}

    if op == "sequence":
        # All args must be TRUE in order; first FALSE/UNKNOWN stops.
        evidence = {"steps": []}
        for i, arg in enumerate(expression.get("args", [])):
            result, reason, ev = evaluate_expression(
                arg, features=features, context=context, direction=direction
            )
            evidence["steps"].append({"i": i, "result": result, "reason": reason, "evidence": ev})
            if result != RuleResult.TRUE:
                return result, reason, evidence
        if not expression.get("args"):
            return RuleResult.UNKNOWN, "empty_sequence", evidence
        return RuleResult.TRUE, None, evidence

    return RuleResult.UNKNOWN, f"unsupported_op:{op}", {}
