"""Step 4 paper promotion confirmation.

Confirms the frozen SOL soak for continued paper trading only. Never enables
live alerts or rolls the model out to other pairs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_strategies.multi_market import MarketRegime, resolve_market_model
from private_trading_strategies.soak_freeze import (
    SOAK_FILL_MODEL,
    SOAK_OBJECTIVE,
    SOAK_SYMBOL,
    assert_soak_freeze,
    soak_incumbent,
    soak_scan_symbols,
)
from private_trading_strategies.specialist_registry import VALIDATED_SPECIALIST_MODELS


def locked_paper_risk_pct(observed_max_drawdown_r: float) -> Decimal:
    """Never raise size after a good soak; optionally cut size after a rough one."""
    base = Decimal(str(SOAK_FILL_MODEL["risk_pct"]))
    if observed_max_drawdown_r > 15:
        return min(base, Decimal("0.25"))
    if observed_max_drawdown_r > 10:
        return min(base, Decimal("0.35"))
    return min(base, Decimal("0.5"))


def evaluate_paper_promotion(step3: dict[str, Any]) -> dict[str, Any]:
    """Fail closed until Step 3 PASS. Live alerts stay blocked either way."""
    blockers: list[str] = []
    try:
        assert_soak_freeze()
    except AssertionError as exc:
        blockers.append(f"soak_freeze_drift:{exc}")

    step3_pass = bool(step3.get("approved_for_paper_promotion"))
    if not step3_pass:
        blockers.append("step3_not_approved")

    incumbent = soak_incumbent()
    if not incumbent.validated_for_paper:
        blockers.append("incumbent_not_validated_for_paper")
    if not incumbent.paper_only or incumbent.live_alerts_allowed:
        blockers.append("incumbent_not_paper_only")
    if VALIDATED_SPECIALIST_MODELS:
        blockers.append("specialist_registry_not_empty")
    if soak_scan_symbols() != (SOAK_SYMBOL,):
        blockers.append("soak_universe_expanded")

    # BTC/ETH stay WAIT. DOGE may have its own paper-only model; that is OK.
    for symbol in ("BTC/USDT", "ETH/USDT", "EUR/USD"):
        if (
            resolve_market_model(
                symbol=symbol,
                regime=MarketRegime.TREND_HIGH_VOL,
                objective=SOAK_OBJECTIVE,
            )
            is not None
        ):
            blockers.append(f"unvalidated_pair_routable:{symbol}")

    observed_dd = float(step3.get("max_drawdown_r") or 0.0)
    risk_pct = locked_paper_risk_pct(observed_dd)
    approved = not blockers
    return {
        "symbol": SOAK_SYMBOL,
        "model_code": incumbent.code,
        "objective": incumbent.objective.value,
        "validated_for_paper": incumbent.validated_for_paper,
        "paper_only": True,
        "live_alerts_allowed": False,
        "other_pairs": "BTC/ETH WAIT; DOGE paper-only if registered",
        "specialists": "empty",
        "observed_max_drawdown_r": observed_dd,
        "locked_risk_pct": str(risk_pct),
        "locked_min_rr": str(incumbent.target_r),
        "locked_max_bars_in_trade": incumbent.max_bars_in_trade,
        "step3_decision": step3.get("decision"),
        "blocking_gates": blockers,
        "step4_complete": approved,
        "soak_confirmed_for_paper": approved,
        "decision": "PASS" if approved else "WAIT",
        "note": (
            "Step 4 confirms paper soak only. Live alerts remain blocked. "
            "Risk is capped from observed drawdown and never raised because "
            "the soak looked good."
        ),
    }
