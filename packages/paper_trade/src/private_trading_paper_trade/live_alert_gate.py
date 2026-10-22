"""Step 5 live-alert readiness gate.

This module never enables live alerts. It only reports whether paper soak is
eligible for a later, explicit release unlock. Default decision is WAIT.
"""

from __future__ import annotations

from typing import Any

from private_trading_strategies.soak_freeze import SOAK_SYMBOL, soak_incumbent


def evaluate_live_alert_decision(
    step4: dict[str, Any],
    *,
    owner_unlock: bool = False,
) -> dict[str, Any]:
    """Fail closed. Even READY still leaves live_alerts_allowed=false here."""
    blockers: list[str] = []
    if not bool(step4.get("soak_confirmed_for_paper")):
        blockers.append("step4_not_confirmed")
    if not owner_unlock:
        blockers.append("owner_unlock_required")

    incumbent = soak_incumbent()
    risk_pct = str(step4.get("locked_risk_pct") or "0.5")
    ready = not blockers
    return {
        "symbol": SOAK_SYMBOL,
        "model_code": incumbent.code,
        "objective": incumbent.objective.value,
        "step4_decision": step4.get("decision"),
        "channel": "telegram",
        "channels_allowed": ["telegram"],
        "locked_risk_pct": risk_pct,
        "max_risk_pct": "0.5",
        "portfolio_gates_required": True,
        "daily_loss_stop_required": True,
        "live_alerts_allowed": False,
        "paper_only": True,
        "owner_unlock": owner_unlock,
        "drawdown_kill_rule": (
            "If any live week max DD exceeds paper holdout DD by >50%, "
            "disable live alerts and revert to paper-only WAIT."
        ),
        "observed_max_drawdown_r": step4.get("observed_max_drawdown_r"),
        "blocking_gates": blockers,
        "step5_complete": ready,
        "eligible_for_release_enable": ready,
        "decision": "READY" if ready else "WAIT",
        "note": (
            "Step 5 never flips release live_alerts_enabled. After READY, an "
            "owner must still unlock through the release checklist. Default is WAIT."
        ),
    }
