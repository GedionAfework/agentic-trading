from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from private_trading_analytics.governance import (
    approve_retrain_request,
    create_retrain_request,
    list_model_governance,
    list_retrain_requests,
    reject_retrain_request,
    retrain_to_dict,
)
from private_trading_analytics.service import (
    create_feedback,
    list_calibration,
    list_feedback,
    list_performance,
    narrate_calibration_snapshot,
    narrate_snapshot,
    refresh_calibration,
    refresh_performance,
    resolve_feedback,
    similar_setups,
    sync_feedback_from_telegram,
)
from private_trading_db.services.audit import record_audit
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.analytics import (
    CalibrationSnapshotOut,
    FeedbackCreate,
    FeedbackOut,
    FeedbackResolve,
    NarrateOut,
    PerformanceSnapshotOut,
    RefreshRequest,
    RetrainApprove,
    RetrainCreate,
    RetrainOut,
    RetrainReject,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _perf_out(snap) -> PerformanceSnapshotOut:
    return PerformanceSnapshotOut(
        id=snap.id,
        cohort=snap.cohort,
        grain=snap.grain,
        strategy_code=snap.strategy_code,
        instrument_symbol=snap.instrument_symbol,
        timeframe=snap.timeframe,
        session_bucket=snap.session_bucket,
        sample_size=snap.sample_size,
        sample_status=snap.sample_status,
        metrics=dict(snap.metrics or {}),
        warnings=list(snap.warnings or []),
        computed_at=snap.computed_at,
    )


def _cal_out(snap) -> CalibrationSnapshotOut:
    return CalibrationSnapshotOut(
        id=snap.id,
        cohort=snap.cohort,
        band_field=snap.band_field,
        sample_size=snap.sample_size,
        sample_status=snap.sample_status,
        bands=dict(snap.bands or {}),
        drift_flags=list(snap.drift_flags or []),
        warnings=list(snap.warnings or []),
        computed_at=snap.computed_at,
    )


def _fb_out(item) -> FeedbackOut:
    return FeedbackOut(
        id=item.id,
        source=item.source,
        source_id=item.source_id,
        candidate_id=item.candidate_id,
        decision_record_id=item.decision_record_id,
        action=item.action,
        status=item.status,
        note=item.note,
        payload=dict(item.payload or {}),
        resolution_note=item.resolution_note,
        resolved_at=item.resolved_at,
        created_at=item.created_at,
    )


def _retrain_out(row) -> RetrainOut:
    data = retrain_to_dict(row)
    return RetrainOut(
        id=row.id,
        decision_model_code=row.decision_model_code,
        reason=row.reason,
        reason_codes=list(row.reason_codes or []),
        evaluation=dict(row.evaluation or {}),
        status=row.status,
        rejection_reason=row.rejection_reason,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        executed_at=row.executed_at,
        resulting_model_ids=list(row.resulting_model_ids or []),
        created_at=row.created_at,
        policy=data["policy"],
    )


@router.get("/performance", response_model=list[PerformanceSnapshotOut])
async def get_performance(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cohort: Annotated[str | None, Query()] = "paper",
    grain: Annotated[str | None, Query()] = None,
) -> list[PerformanceSnapshotOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_performance(
        session, owner_user_id=user.id, cohort=cohort, grain=grain
    )
    return [_perf_out(r) for r in rows]


@router.post("/performance/refresh", response_model=list[PerformanceSnapshotOut])
async def post_performance_refresh(
    body: RefreshRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[PerformanceSnapshotOut]:
    user.require_roles("owner", "admin")
    rows = await refresh_performance(session, owner_user_id=user.id, cohort=body.cohort)
    await record_audit(
        session,
        action="analytics.performance.refresh",
        actor_type="user",
        actor_id=user.id,
        resource_type="performance_snapshot",
        correlation_id=get_correlation_id(request),
        metadata={"cohort": body.cohort, "count": len(rows)},
    )
    await session.commit()
    return [_perf_out(r) for r in rows]


@router.post("/performance/{snapshot_id}/narrate", response_model=NarrateOut)
async def post_performance_narrate(
    snapshot_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NarrateOut:
    user.require_roles("owner", "admin", "viewer")
    result = await narrate_snapshot(
        session, snapshot_id=snapshot_id, owner_user_id=user.id
    )
    return NarrateOut(
        snapshot_id=uuid.UUID(result["snapshot_id"]),
        cohort=result["cohort"],
        narrative=result["narrative"],
    )


@router.get("/calibration", response_model=list[CalibrationSnapshotOut])
async def get_calibration(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cohort: Annotated[str | None, Query()] = "paper",
) -> list[CalibrationSnapshotOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_calibration(session, owner_user_id=user.id, cohort=cohort)
    return [_cal_out(r) for r in rows]


@router.post("/calibration/refresh", response_model=CalibrationSnapshotOut)
async def post_calibration_refresh(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    band_field: Annotated[str, Query()] = "confidence_band",
) -> CalibrationSnapshotOut:
    user.require_roles("owner", "admin")
    snap = await refresh_calibration(
        session, owner_user_id=user.id, cohort="paper", band_field=band_field
    )
    await record_audit(
        session,
        action="analytics.calibration.refresh",
        actor_type="user",
        actor_id=user.id,
        resource_type="calibration_snapshot",
        resource_id=snap.id,
        correlation_id=get_correlation_id(request),
        metadata={"band_field": band_field, "sample_size": snap.sample_size},
    )
    await session.commit()
    return _cal_out(snap)


@router.post("/calibration/{snapshot_id}/narrate", response_model=NarrateOut)
async def post_calibration_narrate(
    snapshot_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NarrateOut:
    user.require_roles("owner", "admin", "viewer")
    result = await narrate_calibration_snapshot(
        session, snapshot_id=snapshot_id, owner_user_id=user.id
    )
    return NarrateOut(
        snapshot_id=uuid.UUID(result["snapshot_id"]),
        cohort=result["cohort"],
        narrative=result["narrative"],
    )


@router.get("/similar/{candidate_id}")
async def get_similar(
    candidate_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    user.require_roles("owner", "admin", "viewer")
    return await similar_setups(
        session, owner_user_id=user.id, candidate_id=candidate_id, limit=limit
    )


@router.get("/feedback", response_model=list[FeedbackOut])
async def get_feedback(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = "open",
) -> list[FeedbackOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_feedback(session, owner_user_id=user.id, status=status)
    return [_fb_out(r) for r in rows]


@router.post("/feedback/sync", response_model=list[FeedbackOut])
async def post_feedback_sync(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FeedbackOut]:
    user.require_roles("owner", "admin")
    rows = await sync_feedback_from_telegram(session, owner_user_id=user.id)
    await session.commit()
    return [_fb_out(r) for r in rows]


@router.post("/feedback", response_model=FeedbackOut)
async def post_feedback(
    body: FeedbackCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackOut:
    user.require_roles("owner", "admin")
    item = await create_feedback(
        session,
        owner_user_id=user.id,
        action=body.action,
        note=body.note,
        candidate_id=body.candidate_id,
        decision_record_id=body.decision_record_id,
    )
    await session.commit()
    return _fb_out(item)


@router.post("/feedback/{item_id}/resolve", response_model=FeedbackOut)
async def post_feedback_resolve(
    item_id: uuid.UUID,
    body: FeedbackResolve,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackOut:
    user.require_roles("owner", "admin")
    item = await resolve_feedback(
        session,
        item_id=item_id,
        owner_user_id=user.id,
        resolver_id=user.id,
        resolution_note=body.resolution_note,
        status=body.status,
    )
    await session.commit()
    return _fb_out(item)


@router.get("/models")
async def get_models(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    user.require_roles("owner", "admin", "viewer")
    return await list_model_governance(session)


@router.get("/retrain", response_model=list[RetrainOut])
async def get_retrain(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RetrainOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_retrain_requests(session, owner_user_id=user.id)
    return [_retrain_out(r) for r in rows]


@router.post("/retrain", response_model=RetrainOut)
async def post_retrain(
    body: RetrainCreate,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RetrainOut:
    user.require_roles("owner", "admin")
    row = await create_retrain_request(
        session,
        owner_user_id=user.id,
        decision_model_code=body.decision_model_code,
        reason=body.reason,
        reason_codes=body.reason_codes,
        evaluation=body.evaluation,
    )
    await record_audit(
        session,
        action="analytics.retrain.request",
        actor_type="user",
        actor_id=user.id,
        resource_type="retrain_request",
        resource_id=row.id,
        correlation_id=get_correlation_id(request),
        metadata={"code": body.decision_model_code, "status": row.status},
    )
    await session.commit()
    return _retrain_out(row)


@router.post("/retrain/{request_id}/approve", response_model=RetrainOut)
async def post_retrain_approve(
    request_id: uuid.UUID,
    body: RetrainApprove,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RetrainOut:
    user.require_roles("owner", "admin")
    row = await approve_retrain_request(
        session,
        request_id=request_id,
        owner_user_id=user.id,
        approver_id=user.id,
        reason_codes=body.reason_codes,
        evaluation=body.evaluation,
    )
    await record_audit(
        session,
        action="analytics.retrain.approve",
        actor_type="user",
        actor_id=user.id,
        resource_type="retrain_request",
        resource_id=row.id,
        correlation_id=get_correlation_id(request),
        metadata={"status": row.status},
    )
    await session.commit()
    return _retrain_out(row)


@router.post("/retrain/{request_id}/reject", response_model=RetrainOut)
async def post_retrain_reject(
    request_id: uuid.UUID,
    body: RetrainReject,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RetrainOut:
    user.require_roles("owner", "admin")
    row = await reject_retrain_request(
        session,
        request_id=request_id,
        owner_user_id=user.id,
        rejection_reason=body.rejection_reason,
    )
    await session.commit()
    return _retrain_out(row)
