from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from private_trading_agents.service import get_decision_record, run_and_persist
from private_trading_agents.vision_service import get_screenshot_job, verdict_from_job
from private_trading_backtest.fixtures import (
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_core.errors import AppError, NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_decision.model_service import get_decision_model, load_model_artifact
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.decisions import DecisionRecordOut, RunDecisionRequest

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _out(record) -> DecisionRecordOut:
    return DecisionRecordOut(
        id=record.id,
        symbol=record.symbol,
        timeframe=record.timeframe,
        bar_open_time=record.bar_open_time,
        action=record.action,
        direction=record.direction,
        setup_state=record.setup_state,
        confidence_band=record.confidence_band,
        strategy_code=record.strategy_code,
        strategy_version_no=record.strategy_version_no,
        risk_approved=record.risk_approved,
        entry_price=_float(record.entry_price),
        stop_price=_float(record.stop_price),
        target_price=_float(record.target_price),
        rr_ratio=_float(record.rr_ratio),
        model_id=record.model_id,
        model_score=_float(record.model_score),
        model_band=record.model_band,
        explanation=record.explanation,
        explanation_source=record.explanation_source,
        evidence=dict(record.evidence or {}),
        workflow=list(record.workflow or []),
        hard_blockers=list(record.hard_blockers or []),
        created_at=record.created_at,
    )


@router.post("/run", response_model=DecisionRecordOut)
async def post_run(
    body: RunDecisionRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionRecordOut:
    user.require_roles("owner", "admin")
    if not body.use_frozen_fixture:
        raise AppError(
            "INVALID_REQUEST",
            "Live candle decisions are not wired yet",
            retryable=False,
        )
    model = None
    model_mode = None
    if body.decision_model_id is not None:
        stored = await get_decision_model(session, body.decision_model_id)
        if stored is None:
            raise NotFoundError("Decision model not found")
        model = load_model_artifact(stored)
        model_mode = stored.mode
    vision = None
    if body.screenshot_job_id is not None:
        shot = await get_screenshot_job(session, body.screenshot_job_id)
        if shot is None:
            raise NotFoundError("Screenshot job not found")
        vision = verdict_from_job(shot)
    record = await run_and_persist(
        session,
        owner_user_id=user.id,
        bars=frozen_bos_long_fixture(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=body.bar_index,
        data_fresh=body.data_fresh,
        market_actionable=body.market_actionable,
        position_state=body.position_state,
        citations=[item.model_dump() for item in body.citations],
        model=model,
        model_id=body.decision_model_id,
        model_mode=model_mode,
        vision=vision,
    )
    await record_audit(
        session,
        action="decision.snapshot_created",
        actor_type="user",
        actor_id=user.id,
        resource_type="decision_record",
        resource_id=record.id,
        correlation_id=get_correlation_id(request),
        metadata={"action": record.action, "setup_state": record.setup_state},
    )
    await session.commit()
    return _out(record)


@router.get("/{record_id}", response_model=DecisionRecordOut)
async def get_record(
    record_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionRecordOut:
    user.require_roles("owner", "admin", "viewer")
    record = await get_decision_record(session, record_id)
    if record is None:
        raise NotFoundError("Decision record not found")
    return _out(record)
