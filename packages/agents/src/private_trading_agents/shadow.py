"""Agentic shadow compare for paper soak.

Primary decisions stay deterministic. When enabled, agentic runs in shadow only:
compare actions/gates, attach evidence, never override ENTER/WAIT/paper opens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from private_trading_agents.workflow import DecisionSnapshot, run_decision_workflow

_COMPARE_FIELDS = (
    "action",
    "setup_state",
    "risk_approved",
    "direction",
    "strategy_code",
    "strategy_version_no",
    "hard_blockers",
    "confidence_band",
)


@dataclass(slots=True)
class ShadowCompareResult:
    parity: bool
    mismatched_fields: list[str] = field(default_factory=list)
    primary_action: str = ""
    shadow_action: str | None = None
    shadow_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "parity": self.parity,
            "mismatched_fields": list(self.mismatched_fields),
            "primary_action": self.primary_action,
            "shadow_action": self.shadow_action,
            "shadow_error": self.shadow_error,
            "primary_mode": "deterministic",
            "shadow_mode": "agentic",
            "overrides_primary": False,
        }


def compare_decision_snapshots(
    primary: DecisionSnapshot,
    shadow: DecisionSnapshot,
) -> ShadowCompareResult:
    mismatched: list[str] = []
    for name in _COMPARE_FIELDS:
        left = getattr(primary, name)
        right = getattr(shadow, name)
        if left != right:
            mismatched.append(name)
    return ShadowCompareResult(
        parity=not mismatched,
        mismatched_fields=mismatched,
        primary_action=primary.action.value,
        shadow_action=shadow.action.value,
    )


def attach_shadow_evidence(
    primary: DecisionSnapshot,
    compare: ShadowCompareResult,
) -> DecisionSnapshot:
    """Copy primary snapshot with shadow compare evidence (action unchanged)."""
    from dataclasses import replace

    evidence = dict(primary.evidence)
    evidence["agentic_shadow"] = compare.as_dict()
    return replace(primary, evidence=evidence)


def shadow_agentic_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    try:
        from private_trading_core.config import get_settings

        return bool(get_settings().agentic_shadow_enabled)
    except Exception:  # noqa: BLE001 — fail closed (shadow off)
        return False


def run_decision_with_optional_shadow(
    bars: list,
    *,
    shadow: bool | None = None,
    mode: Literal["deterministic", "agentic"] = "deterministic",
    **workflow_kwargs: Any,
) -> DecisionSnapshot:
    """Run primary workflow; optionally shadow-compare agentic without overriding.

    Paper/scanner must pass mode='deterministic' (default). Shadow never changes
    the returned action — mismatches are evidence only.
    """
    primary = run_decision_workflow(bars, mode=mode, **workflow_kwargs)
    if mode != "deterministic" or not shadow_agentic_enabled(shadow):
        return primary

    try:
        shadow_snap = run_decision_workflow(bars, mode="agentic", **workflow_kwargs)
        compare = compare_decision_snapshots(primary, shadow_snap)
    except Exception as exc:  # noqa: BLE001 — shadow must never break primary
        compare = ShadowCompareResult(
            parity=False,
            mismatched_fields=["shadow_error"],
            primary_action=primary.action.value,
            shadow_action=None,
            shadow_error=f"{type(exc).__name__}: {exc}"[:500],
        )
    return attach_shadow_evidence(primary, compare)
