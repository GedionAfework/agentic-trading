from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.backtest import BacktestDataset, BacktestJob
from private_trading_features.engine import FEATURE_ENGINE_VERSION
from private_trading_features.types import CandleBar
from private_trading_risk.policy import RISK_ENGINE_VERSION
from private_trading_strategies.evaluate import STRATEGY_ENGINE_VERSION
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_backtest.fingerprint import bar_to_dict, bars_from_dicts, dataset_fingerprint
from private_trading_backtest.fixtures import (
    FIXTURE_CODE,
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_backtest.replay import BACKTEST_ENGINE_VERSION, report_to_dict, run_replay


async def ensure_frozen_fixture_dataset(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> BacktestDataset:
    bars = frozen_bos_long_fixture()
    fp = dataset_fingerprint(bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME)
    existing = await session.execute(
        select(BacktestDataset).where(
            BacktestDataset.owner_user_id == owner_user_id,
            BacktestDataset.code == FIXTURE_CODE,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    dataset = BacktestDataset(
        owner_user_id=owner_user_id,
        code=FIXTURE_CODE,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        source="fixture",
        fingerprint=fp,
        bar_count=len(bars),
        bars_json=[bar_to_dict(b) for b in bars],
        meta={"description": "Frozen BOS long regression fixture"},
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset


def load_dataset_bars(dataset: BacktestDataset) -> list[CandleBar]:
    if not dataset.bars_json:
        raise AppError("DATASET_EMPTY", "Dataset has no bars", retryable=False)
    return bars_from_dicts(list(dataset.bars_json))


async def create_dataset_from_bars(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    code: str,
    symbol: str,
    timeframe: str,
    bars: list[CandleBar],
    source: str = "upload",
) -> BacktestDataset:
    if not bars:
        raise AppError("DATASET_EMPTY", "No bars provided", retryable=False)
    fp = dataset_fingerprint(bars, symbol=symbol, timeframe=timeframe)
    clash = await session.execute(select(BacktestDataset).where(BacktestDataset.fingerprint == fp))
    existing_fp = clash.scalar_one_or_none()
    if existing_fp is not None:
        return existing_fp

    dataset = BacktestDataset(
        owner_user_id=owner_user_id,
        code=code,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        fingerprint=fp,
        bar_count=len(bars),
        bars_json=[bar_to_dict(b) for b in bars],
        meta={},
    )
    session.add(dataset)
    try:
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise AppError("DATASET_CREATE_FAILED", "Could not create dataset", retryable=False) from exc
    await session.refresh(dataset)
    return dataset


async def get_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> BacktestDataset | None:
    result = await session.execute(select(BacktestDataset).where(BacktestDataset.id == dataset_id))
    return result.scalar_one_or_none()


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> BacktestJob | None:
    result = await session.execute(
        select(BacktestJob)
        .options(selectinload(BacktestJob.dataset))
        .where(BacktestJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def list_jobs(session: AsyncSession, *, owner_user_id: uuid.UUID) -> list[BacktestJob]:
    result = await session.execute(
        select(BacktestJob)
        .where(BacktestJob.owner_user_id == owner_user_id)
        .order_by(BacktestJob.created_at.desc())
    )
    return list(result.scalars().all())


async def run_backtest_job(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    config: dict[str, Any] | None = None,
) -> BacktestJob:
    dataset = await get_dataset(session, dataset_id)
    if dataset is None:
        raise AppError("NOT_FOUND", "Dataset not found", retryable=False)

    bars = load_dataset_bars(dataset)
    job = BacktestJob(
        owner_user_id=owner_user_id,
        dataset_id=dataset.id,
        strategy_code="wyckoff-hdm",
        strategy_version_no=1,
        risk_policy_code="default-crypto",
        risk_policy_version_no=1,
        status="running",
        config=config or {},
        report={},
        engine_version=BACKTEST_ENGINE_VERSION,
        feature_engine_version=FEATURE_ENGINE_VERSION,
        strategy_engine_version=STRATEGY_ENGINE_VERSION,
        risk_engine_version=RISK_ENGINE_VERSION,
        dataset_fingerprint=dataset.fingerprint,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    try:
        report = run_replay(
            bars,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            dataset_fingerprint=dataset.fingerprint,
            config=config,
        )
        job.report = report_to_dict(report)
        job.status = "succeeded"
        job.completed_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = datetime.now(UTC)
        job.report = {"error": str(exc)}
        await session.commit()
        raise AppError("BACKTEST_FAILED", "Backtest failed", retryable=False) from exc

    await session.commit()
    await session.refresh(job)
    return job
