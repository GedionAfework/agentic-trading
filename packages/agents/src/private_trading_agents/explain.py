from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _fmt(value: Decimal | float | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def allowed_numbers(facts: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for key in ("entry_price", "stop_price", "target_price", "rr_ratio", "model_score"):
        text = _fmt(facts.get(key))
        if text:
            allowed.add(text)
            allowed.add(text.rstrip("0").rstrip(".") if "." in text else text)
    for token in facts.get("extra_numbers") or []:
        allowed.add(str(token))
    return allowed


def explanation_invents_numbers(text: str, facts: dict[str, Any]) -> list[str]:
    allowed = allowed_numbers(facts)
    invented: list[str] = []
    for match in _NUMBER.findall(text):
        if match in {"0", "1", "2"} and match in text:
            # Version numbers and small counts are cited from strategy version / rule counts.
            if match in allowed or match == str(facts.get("strategy_version_no")):
                continue
            if match == "1" or match == "2":
                continue
        if match not in allowed and match != str(facts.get("strategy_version_no")):
            invented.append(match)
    return invented


def grounded_explanation(facts: dict[str, Any]) -> str:
    """Narrative that only restates engine outputs and supplied citations."""
    action = facts["action"]
    parts = [
        (
        f"Action {action} on {facts['symbol']} {facts['timeframe']}. "
        "Bar open time is stored on the decision record."
        ),
        (
            f"Strategy {facts['strategy_code']} version {facts['strategy_version_no']} "
            f"setup_state={facts['setup_state']}."
        ),
    ]
    blockers = facts.get("hard_blockers") or []
    if blockers:
        parts.append("Hard blockers: " + ", ".join(blockers) + ".")
    else:
        parts.append("Hard blockers: none.")
    entry = _fmt(facts.get("entry_price"))
    stop = _fmt(facts.get("stop_price"))
    target = _fmt(facts.get("target_price"))
    rr = _fmt(facts.get("rr_ratio"))
    if entry and stop and target:
        parts.append(
            f"Risk engine entry {entry}, stop {stop}, target {target}, rr {rr}."
        )
    else:
        parts.append("Risk engine did not produce a complete entry, stop, and target.")
    parts.append(f"Risk approved={str(bool(facts['risk_approved'])).lower()}.")
    feature_bits = []
    for name, payload in (facts.get("features") or {}).items():
        feature_bits.append(f"{name}={payload.get('status')}")
    if feature_bits:
        parts.append("Features: " + ", ".join(feature_bits) + ".")
    citations = facts.get("citations") or []
    if citations:
        ids = ", ".join(item["citation_id"] for item in citations)
        parts.append(f"Knowledge citations: {ids}.")
    else:
        parts.append("Knowledge citations: none. Evidence is insufficient to add course claims.")
    if facts.get("model_score") is not None:
        parts.append(
            f"Rank score {_fmt(facts['model_score'])} band {facts.get('model_band')} "
            "is not a probability."
        )
    elif facts.get("model_invoked"):
        parts.append("Ranker abstained. No probability is stated.")
    parts.append(f"Confidence band {facts['confidence_band']}.")
    parts.append("Numeric fields are copied from the feature, strategy, risk, and ranker outputs.")
    text = " ".join(parts)
    invented = explanation_invents_numbers(text, facts)
    if invented:
        raise ValueError(f"explanation invented numbers: {invented}")
    return text
