from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_risk.policy import RISK_ENGINE_VERSION, as_decimal, default_policy_config
from private_trading_risk.sizing import paper_quantity, risk_reward, stop_is_valid_for_direction
from private_trading_risk.types import (
    Direction,
    PaperSizeSuggestion,
    RiskAssessmentResult,
    RiskInput,
    WeekendPolicy,
)
from private_trading_risk.vocabulary import vocabulary_violations


def assess_risk(
    *,
    policy_code: str,
    policy_version_no: int,
    policy_config: dict[str, Any] | None,
    risk_input: RiskInput,
) -> RiskAssessmentResult:
    cfg = default_policy_config(**(policy_config or {}))
    blockers: list[str] = []
    warnings: list[str] = []

    entry = risk_input.entry
    stop = risk_input.stop
    target = risk_input.target_1
    direction = risk_input.direction

    risk_distance: Decimal | None = None
    reward_distance: Decimal | None = None
    rr_ratio: Decimal | None = None

    if cfg.get("require_invalidation", True):
        if stop is None:
            blockers.append("missing_invalidation")
        if entry is None:
            blockers.append("missing_entry")
        if entry is not None and stop is not None:
            if entry == stop:
                blockers.append("entry_equals_stop")
            elif not stop_is_valid_for_direction(direction=direction, entry=entry, stop=stop):
                blockers.append("stop_wrong_side_of_entry")

    if target is None:
        blockers.append("missing_target_1")

    if entry is not None and stop is not None and target is not None:
        if "entry_equals_stop" not in blockers and "stop_wrong_side_of_entry" not in blockers:
            try:
                risk_distance, reward_distance, rr_ratio = risk_reward(
                    direction=direction, entry=entry, stop=stop, target=target
                )
            except ValueError as exc:
                blockers.append(str(exc))

    min_rr = as_decimal(cfg.get("min_rr", 2.0))
    if rr_ratio is not None and rr_ratio < min_rr:
        blockers.append(f"rr_below_minimum:{rr_ratio}:{min_rr}")

    if cfg.get("require_fresh_data", True):
        if not risk_input.data_fresh:
            blockers.append("stale_market_data")
        if not risk_input.market_actionable:
            blockers.append("market_not_actionable")

    weekend_policy = WeekendPolicy(str(cfg.get("weekend_policy", WeekendPolicy.WARN.value)))
    if risk_input.is_weekend:
        if weekend_policy == WeekendPolicy.HARD_BLOCK:
            blockers.append("weekend_policy_hard_block")
        elif weekend_policy == WeekendPolicy.WARN:
            warnings.append("weekend_policy_warning")

    if cfg.get("event_blackout_enabled") and risk_input.in_event_blackout:
        blockers.append("event_blackout")
    elif risk_input.in_event_blackout and not cfg.get("event_blackout_enabled"):
        warnings.append("event_blackout_unconfigured")

    max_open = as_decimal(cfg.get("max_open_risk_pct", 2.0))
    if risk_input.open_risk_pct is not None and risk_input.open_risk_pct > max_open:
        blockers.append(f"open_risk_exceeded:{risk_input.open_risk_pct}:{max_open}")

    vocab_hits = vocabulary_violations(risk_input.summary_text)
    if vocab_hits:
        blockers.append("forbidden_certainty_language")
        warnings.extend(f"vocab:{h}" for h in vocab_hits)

    paper: PaperSizeSuggestion | None = None
    if cfg.get("allow_paper_sizing", True) and entry is not None and stop is not None:
        risk_pct = as_decimal(cfg.get("max_risk_pct", 0.5))
        equity = risk_input.account_equity
        qty, notional, notes = (None, None, [])
        risk_amount = None
        if equity is not None:
            risk_amount = equity * (risk_pct / Decimal("100"))
            qty, notional, notes = paper_quantity(
                equity=equity,
                risk_pct=risk_pct,
                entry=entry,
                stop=stop,
                instrument=risk_input.instrument,
            )
        else:
            notes = ["equity_not_provided"]
            warnings.append("paper_sizing_skipped_no_equity")
        paper = PaperSizeSuggestion(
            risk_pct=risk_pct,
            risk_amount=risk_amount,
            quantity=qty,
            notional=notional,
            notes=notes,
        )
        if "below_min_notional" in notes:
            warnings.append("below_min_notional")

    approved = len(blockers) == 0
    return RiskAssessmentResult(
        approved=approved,
        direction=direction,
        entry_reference=entry,
        stop_price=stop,
        target_1=target,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        rr_ratio=rr_ratio,
        hard_blockers=blockers,
        warnings=warnings,
        paper_size=paper,
        engine_version=RISK_ENGINE_VERSION,
        policy_code=policy_code,
        policy_version_no=policy_version_no,
        meta={
            "lock_status": cfg.get("lock_status"),
            "decision_refs": cfg.get("decision_refs", []),
            "never_places_live_orders": True,
        },
    )
