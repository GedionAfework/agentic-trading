from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from private_trading_agents.vision import evaluate_gate_d
from private_trading_agents.vision_service import (
    analyze_screenshot,
    correct_screenshot,
    get_screenshot_job,
)
from private_trading_core.errors import AppError, NotFoundError
from private_trading_db.services.audit import record_audit
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.vision import (
    CorrectScreenshotRequest,
    GateDReport,
    ScreenshotJobOut,
)

router = APIRouter(prefix="/vision", tags=["vision"])


def _out(job) -> ScreenshotJobOut:
    return ScreenshotJobOut(
        id=job.id,
        status=job.status,
        content_type=job.content_type,
        byte_size=job.byte_size,
        market_symbol=job.market_symbol,
        market_timeframe=job.market_timeframe,
        extraction=dict(job.extraction or {}),
        verification=dict(job.verification or {}),
        authorizes_trade=job.authorizes_trade,
        corrected_symbol=job.corrected_symbol,
        corrected_timeframe=job.corrected_timeframe,
        retain_until=job.retain_until,
        created_at=job.created_at,
    )


@router.post("/screenshots", response_model=ScreenshotJobOut)
async def post_screenshot(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    market_symbol: Annotated[str | None, Form()] = None,
    market_timeframe: Annotated[str | None, Form()] = None,
    vlm_json: Annotated[str | None, Form()] = None,
) -> ScreenshotJobOut:
    user.require_roles("owner", "admin")
    payload = None
    if vlm_json:
        try:
            payload = json.loads(vlm_json)
        except json.JSONDecodeError as exc:
            raise AppError(
                "INVALID_REQUEST",
                "vlm_json is not valid JSON",
                retryable=False,
            ) from exc
        if not isinstance(payload, dict):
            raise AppError("INVALID_REQUEST", "vlm_json must be an object", retryable=False)
    data = await file.read()
    job = await analyze_screenshot(
        session,
        owner_user_id=user.id,
        data=data,
        content_type=file.content_type,
        market_symbol=market_symbol,
        market_timeframe=market_timeframe,
        vlm_payload=payload,
    )
    await record_audit(
        session,
        action="vision.screenshot_analyzed",
        actor_type="user",
        actor_id=user.id,
        resource_type="screenshot_job",
        resource_id=job.id,
        correlation_id=get_correlation_id(request),
        metadata={"status": job.status, "authorizes_trade": False},
    )
    await session.commit()
    return _out(job)


@router.get("/screenshots/{job_id}", response_model=ScreenshotJobOut)
async def get_screenshot(
    job_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScreenshotJobOut:
    user.require_roles("owner", "admin", "viewer")
    job = await get_screenshot_job(session, job_id)
    if job is None:
        raise NotFoundError("Screenshot job not found")
    return _out(job)


@router.post("/screenshots/{job_id}/correct", response_model=ScreenshotJobOut)
async def post_correct(
    job_id: uuid.UUID,
    body: CorrectScreenshotRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScreenshotJobOut:
    user.require_roles("owner", "admin")
    job = await correct_screenshot(
        session,
        job_id=job_id,
        actor_user_id=user.id,
        symbol=body.symbol,
        timeframe=body.timeframe,
    )
    await record_audit(
        session,
        action="vision.screenshot_corrected",
        actor_type="user",
        actor_id=user.id,
        resource_type="screenshot_job",
        resource_id=job.id,
        correlation_id=get_correlation_id(request),
        metadata={"symbol": job.corrected_symbol, "timeframe": job.corrected_timeframe},
    )
    await session.commit()
    return _out(job)


@router.post("/benchmark", response_model=GateDReport)
async def post_benchmark(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GateDReport:
    user.require_roles("owner", "admin", "viewer")
    return GateDReport.model_validate(evaluate_gate_d())
