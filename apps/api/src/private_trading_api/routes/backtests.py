from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from private_trading_core.errors import NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_backtest.service import (
    ensure_frozen_fixture_dataset,
    get_job,
    list_jobs,
    run_backtest_job,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.backtests import DatasetOut, JobOut, RunBacktestRequest

router = APIRouter(prefix="/backtests", tags=["backtests"])


def _job_out(job) -> JobOut:
    return JobOut(
        id=job.id,
        dataset_id=job.dataset_id,
        status=job.status,
        strategy_code=job.strategy_code,
        strategy_version_no=job.strategy_version_no,
        risk_policy_code=job.risk_policy_code,
        risk_policy_version_no=job.risk_policy_version_no,
        engine_version=job.engine_version,
        feature_engine_version=job.feature_engine_version,
        strategy_engine_version=job.strategy_engine_version,
        risk_engine_version=job.risk_engine_version,
        dataset_fingerprint=job.dataset_fingerprint,
        report=dict(job.report or {}),
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post("/datasets/ensure-frozen", response_model=DatasetOut)
async def post_ensure_frozen(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetOut:
    user.require_roles("owner", "admin")
    dataset = await ensure_frozen_fixture_dataset(session, owner_user_id=user.id)
    await record_audit(
        session,
        action="backtest.dataset_ensure_frozen",
        actor_type="user",
        actor_id=user.id,
        resource_type="backtest_dataset",
        resource_id=dataset.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return DatasetOut(
        id=dataset.id,
        code=dataset.code,
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        fingerprint=dataset.fingerprint,
        bar_count=dataset.bar_count,
        created_at=dataset.created_at,
    )


@router.post("/jobs", response_model=JobOut)
async def post_run_job(
    body: RunBacktestRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    user.require_roles("owner", "admin")
    dataset_id = body.dataset_id
    if dataset_id is None:
        if not body.use_frozen_fixture:
            raise NotFoundError("dataset_id required when use_frozen_fixture is false")
        dataset = await ensure_frozen_fixture_dataset(session, owner_user_id=user.id)
        dataset_id = dataset.id

    job = await run_backtest_job(
        session,
        owner_user_id=user.id,
        dataset_id=dataset_id,
        config=body.config,
    )
    await record_audit(
        session,
        action="backtest.job_completed",
        actor_type="user",
        actor_id=user.id,
        resource_type="backtest_job",
        resource_id=job.id,
        correlation_id=get_correlation_id(request),
        metadata={"status": job.status, "fingerprint": job.dataset_fingerprint},
    )
    await session.commit()
    return _job_out(job)


@router.get("/jobs", response_model=list[JobOut])
async def get_jobs(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[JobOut]:
    user.require_roles("owner", "admin", "viewer")
    return [_job_out(j) for j in await list_jobs(session, owner_user_id=user.id)]


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job_detail(
    job_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    user.require_roles("owner", "admin", "viewer")
    job = await get_job(session, job_id)
    if job is None:
        raise NotFoundError("Backtest job not found")
    return _job_out(job)
