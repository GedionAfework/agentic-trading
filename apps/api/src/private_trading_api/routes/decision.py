from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from private_trading_core.errors import NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_decision.model_service import (
    get_decision_model,
    list_decision_models,
    predict_with_model,
    promote_decision_model,
    train_registered_dataset,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.decision import (
    DecisionModelOut,
    PredictDecisionRequest,
    PredictDecisionResponse,
    TrainDecisionRequest,
    TrainDecisionResponse,
)

router = APIRouter(prefix="/decision", tags=["decision"])


def _out(model) -> DecisionModelOut:
    importance = model.feature_importance or []
    return DecisionModelOut(
        id=model.id,
        code=model.code,
        name=model.name,
        algorithm=model.algorithm,
        role=model.role,
        mode=model.mode,
        status=model.status,
        fingerprint=model.fingerprint,
        training_dataset_version_id=model.training_dataset_version_id,
        training_window=dict(model.training_window or {}),
        metrics=dict(model.metrics or {}),
        feature_importance=[dict(item) for item in importance],
        hyperparameters=dict(model.hyperparameters or {}),
        engine_version=model.engine_version,
        created_at=model.created_at,
        promoted_at=model.promoted_at,
    )


@router.get("/models", response_model=list[DecisionModelOut])
async def get_models(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DecisionModelOut]:
    user.require_roles("owner", "admin", "viewer")
    return [_out(m) for m in await list_decision_models(session)]


@router.post("/models/train", response_model=TrainDecisionResponse)
async def post_train(
    body: TrainDecisionRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainDecisionResponse:
    user.require_roles("owner", "admin")
    baseline, challenger, recommended = await train_registered_dataset(
        session,
        owner_user_id=user.id,
        training_version_id=body.training_version_id,
        code=body.code,
        name=body.name,
    )
    await record_audit(
        session,
        action="decision.models_trained",
        actor_type="user",
        actor_id=user.id,
        resource_type="decision_model",
        resource_id=challenger.id,
        correlation_id=get_correlation_id(request),
        metadata={"recommended_role": recommended, "code": body.code},
    )
    await session.commit()
    return TrainDecisionResponse(
        baseline=_out(baseline),
        challenger=_out(challenger),
        recommended_role=recommended,
    )


@router.post("/models/{model_id}/promote", response_model=DecisionModelOut)
async def post_promote(
    model_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionModelOut:
    user.require_roles("owner", "admin")
    model = await promote_decision_model(session, model_id=model_id)
    await record_audit(
        session,
        action="decision.model_promoted",
        actor_type="user",
        actor_id=user.id,
        resource_type="decision_model",
        resource_id=model.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return _out(model)


@router.post("/models/{model_id}/predict", response_model=PredictDecisionResponse)
async def post_predict(
    model_id: uuid.UUID,
    body: PredictDecisionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PredictDecisionResponse:
    user.require_roles("owner", "admin", "viewer")
    model = await get_decision_model(session, model_id)
    if model is None:
        raise NotFoundError("Decision model not found")
    decision = predict_with_model(
        model,
        body.features,
        strategy_ready=body.strategy_ready,
        risk_approved=body.risk_approved,
        hard_blockers=body.hard_blockers,
    )
    return PredictDecisionResponse(
        model_id=model.id,
        mode=model.mode,
        recommendation=decision.recommendation,
        reason=decision.reason,
        score=decision.score,
        band=decision.band,
        abstained=decision.abstained,
        gates_passed=decision.gates_passed,
        hard_blockers=decision.hard_blockers,
        score_kind=decision.score_kind,
        not_a_calibrated_probability=decision.not_a_calibrated_probability,
        llm_may_invent_probability=decision.llm_may_invent_probability,
        cannot_bypass_strategy_or_risk=decision.cannot_bypass_strategy_or_risk,
    )
