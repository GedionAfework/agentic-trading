"""Deterministic tool handlers. Invoked only through the gated runtime."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from private_trading_decision.labels import FEATURE_NAMES
from private_trading_features.engine import compute_feature
from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import default_policy_config
from private_trading_risk.types import Direction as RiskDirection
from private_trading_risk.types import InstrumentRiskMeta, RiskInput
from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import evaluate_strategy
from private_trading_strategies.types import Direction, SetupState
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

from private_trading_agents.adapters import (
    feature_models_to_payload,
    feature_payload_to_models,
    models_to_candles,
)
from private_trading_agents.explain import grounded_explanation
from private_trading_agents.tools.schemas import (
    ExplainGroundedIn,
    ExplainGroundedOut,
    FeaturesComputeIn,
    FeaturesComputeOut,
    MlRankIn,
    MlRankOut,
    RiskAssessIn,
    RiskAssessOut,
    SignalCheckGatesIn,
    SignalCheckGatesOut,
    StrategyEvaluateIn,
    StrategyEvaluateOut,
    VisionCheckVerdictIn,
    VisionCheckVerdictOut,
)


def handle_features_compute(payload: FeaturesComputeIn) -> FeaturesComputeOut:
    bars = models_to_candles(payload.bars)
    index = len(bars) - 1 if payload.bar_index is None else payload.bar_index
    if index < 0 or index >= len(bars):
        raise ValueError("bar_index out of range")
    names = payload.feature_names or list(FEATURE_NAMES)
    raw: dict = {}
    for name in names:
        value = compute_feature(name, bars, index)
        numeric = value.value
        if hasattr(numeric, "__float__") and numeric is not None:
            try:
                if isinstance(numeric, Decimal):
                    numeric = float(numeric)
            except Exception:  # noqa: BLE001
                pass
        raw[name] = {
            "status": value.status.value,
            "value": numeric,
            "reason": value.reason,
        }
    return FeaturesComputeOut(
        bar_index=index,
        bar_open_time=bars[index].open_time,
        features=feature_payload_to_models(raw),
    )


def handle_strategy_evaluate(payload: StrategyEvaluateIn) -> StrategyEvaluateOut:
    bars = models_to_candles(payload.bars)
    side = Direction(payload.direction)
    features = feature_models_to_payload(payload.features)
    ctx = build_playbook_context(
        bars,
        payload.bar_index,
        direction=side,
        min_rr=payload.min_rr,
        entry_path=DEFAULT_ENTRY_PATH,
    )
    entry = Decimal(str(ctx["_entry_ref"])) if ctx.get("_entry_ref") else None
    stop = Decimal(str(ctx["_stop_price"])) if ctx.get("_stop_price") else None
    target = None
    if entry is not None and stop is not None:
        risk = abs(entry - stop)
        if risk > 0:
            target = (
                entry + risk * payload.min_rr
                if side == Direction.LONG
                else entry - risk * payload.min_rr
            )
    strategy = build_wyckoff_hdm_v1(
        version_no=1, advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    assessment = evaluate_strategy(
        strategy,
        direction=side,
        features=features,
        context={k: v for k, v in ctx.items() if not k.startswith("_")},
    )
    return StrategyEvaluateOut(
        strategy_code=assessment.strategy_code,
        strategy_version_no=assessment.strategy_version_no,
        setup_state=assessment.setup_state.value,
        direction=side.value,
        blockers=list(assessment.blockers),
        warnings=list(assessment.warnings),
        entry_price=entry,
        stop_price=stop,
        target_price=target,
    )


def handle_risk_assess(payload: RiskAssessIn) -> RiskAssessOut:
    asset_class = payload.asset_class
    risk = assess_risk(
        policy_code=f"default-{asset_class}",
        policy_version_no=1,
        policy_config=default_policy_config(asset_class=asset_class),
        risk_input=RiskInput(
            direction=RiskDirection(payload.direction),
            entry=payload.entry,
            stop=payload.stop,
            target_1=payload.target,
            data_fresh=payload.data_fresh,
            market_actionable=payload.market_actionable,
            account_equity=payload.account_equity,
            instrument=InstrumentRiskMeta(
                asset_class=asset_class,
                price_tick=(
                    Decimal("0.00001")
                    if asset_class == "forex"
                    else Decimal("0.01")
                ),
                qty_step=(
                    Decimal("0.01") if asset_class == "forex" else Decimal("0.001")
                ),
                min_notional=(
                    Decimal("0") if asset_class == "forex" else Decimal("10")
                ),
            ),
        ),
    )
    blockers = list(payload.prior_blockers)
    for blocker in risk.hard_blockers:
        if blocker not in blockers:
            blockers.append(blocker)
    return RiskAssessOut(
        approved=risk.approved,
        entry_price=(
            risk.entry_reference if risk.entry_reference is not None else payload.entry
        ),
        stop_price=risk.stop_price if risk.stop_price is not None else payload.stop,
        target_price=risk.target_1 if risk.target_1 is not None else payload.target,
        rr_ratio=risk.rr_ratio,
        hard_blockers=blockers,
        warnings=list(risk.warnings),
    )


def handle_explain_grounded(payload: ExplainGroundedIn) -> ExplainGroundedOut:
    return ExplainGroundedOut(
        explanation=grounded_explanation(payload.facts),
        explanation_source="deterministic",
    )


def handle_signal_check_gates(payload: SignalCheckGatesIn) -> SignalCheckGatesOut:
    blockers = list(payload.hard_blockers)
    if not payload.data_fresh and "stale_market_data" not in blockers:
        blockers.append("stale_market_data")
    if not payload.market_actionable and "market_not_actionable" not in blockers:
        blockers.append("market_not_actionable")
    ready = payload.setup_state == SetupState.READY_FOR_REVIEW.value
    gates_open_candidate = (
        payload.data_fresh and payload.market_actionable and ready
    )
    return SignalCheckGatesOut(
        gates_open_candidate=gates_open_candidate,
        hard_blockers=blockers,
    )


def handle_vision_check_verdict(
    payload: VisionCheckVerdictIn,
) -> VisionCheckVerdictOut:
    if not payload.attached:
        return VisionCheckVerdictOut(
            skipped=True,
            needs_clarification=False,
            blocker=None,
            status="skipped",
        )
    return VisionCheckVerdictOut(
        skipped=False,
        needs_clarification=payload.needs_clarification,
        blocker=payload.blocker,
        status=payload.status or "ok",
    )


def handle_ml_rank(payload: MlRankIn, *, context: Any | None = None) -> MlRankOut:
    model = context.model if context is not None else None
    if model is None or not payload.model_present or not payload.gates_open:
        return MlRankOut(
            invoked=False,
            status="skipped",
            note="ranker omitted or gates already closed",
        )
    features = feature_models_to_payload(payload.features)
    ranked = model.decide(
        features,
        strategy_ready=True,
        risk_approved=True,
        mode=payload.model_mode or "shadow",
    )
    return MlRankOut(
        invoked=True,
        model_score=ranked.score,
        model_band=ranked.band,
        recommends_enter=ranked.recommendation == "ENTER",
        status="scored",
        note=f"band={ranked.band} mode={payload.model_mode or 'shadow'}",
    )
