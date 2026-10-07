from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from private_trading_backtest.fingerprint import bars_from_dicts
from private_trading_backtest.fixtures import (
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_backtest.fingerprint import dataset_fingerprint as ohlcv_fingerprint
from private_trading_core.errors import AppError
from private_trading_db.models.backtest import BacktestDataset
from private_trading_db.models.training import TrainingDataset, TrainingDatasetVersion
from private_trading_knowledge.storage import LocalObjectStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_decision.builder import build_training_dataset, serialize_rows_jsonl
from private_trading_decision.types import LabelPolicy


async def get_training_dataset_by_code(
    session: AsyncSession, code: str
) -> TrainingDataset | None:
    result = await session.execute(
        select(TrainingDataset)
        .options(selectinload(TrainingDataset.versions))
        .where(TrainingDataset.code == code)
    )
    return result.scalar_one_or_none()


async def get_training_version(
    session: AsyncSession, version_id: uuid.UUID
) -> tuple[TrainingDataset, TrainingDatasetVersion] | None:
    result = await session.execute(
        select(TrainingDatasetVersion)
        .options(selectinload(TrainingDatasetVersion.dataset))
        .where(TrainingDatasetVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return None
    return version.dataset, version


async def build_and_register(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    code: str = "frozen_bos_long_train_v1",
    name: str = "Frozen BOS long training set",
    backtest_dataset_id: uuid.UUID | None = None,
    use_frozen_fixture: bool = True,
    split_mode: Literal["time", "walk_forward"] = "time",
    label_policy: LabelPolicy | None = None,
) -> TrainingDatasetVersion:
    if backtest_dataset_id is not None:
        result = await session.execute(
            select(BacktestDataset).where(BacktestDataset.id == backtest_dataset_id)
        )
        source = result.scalar_one_or_none()
        if source is None or not source.bars_json:
            raise AppError("NOT_FOUND", "Backtest dataset not found or empty", retryable=False)
        bars = bars_from_dicts(list(source.bars_json))
        symbol = source.symbol
        timeframe = source.timeframe
        source_fp = source.fingerprint
    elif use_frozen_fixture:
        bars = frozen_bos_long_fixture()
        symbol = FIXTURE_SYMBOL
        timeframe = FIXTURE_TIMEFRAME
        source_fp = ohlcv_fingerprint(bars, symbol=symbol, timeframe=timeframe)
    else:
        raise AppError("INVALID_REQUEST", "Provide backtest_dataset_id or use_frozen_fixture", retryable=False)

    policy = label_policy or LabelPolicy()
    built = build_training_dataset(
        bars,
        symbol=symbol,
        timeframe=timeframe,
        source_dataset_fingerprint=source_fp,
        policy=policy,
        split_mode=split_mode,
    )

    storage = LocalObjectStorage()
    payload = serialize_rows_jsonl(built.rows)
    object_key, _sha = storage.put_bytes(payload, suffix=".jsonl")

    dataset = await get_training_dataset_by_code(session, code)
    if dataset is None:
        dataset = TrainingDataset(
            owner_user_id=owner_user_id,
            code=code,
            name=name,
            description="Phase 10 training rows with lineage pins",
            status="active",
        )
        session.add(dataset)
        await session.flush()
        version_no = 1
    else:
        version_no = max((v.version_no for v in dataset.versions), default=0) + 1

    # Idempotent on fingerprint
    existing_fp = await session.execute(
        select(TrainingDatasetVersion).where(TrainingDatasetVersion.fingerprint == built.fingerprint)
    )
    prior = existing_fp.scalar_one_or_none()
    if prior is not None:
        return prior

    version = TrainingDatasetVersion(
        dataset_id=dataset.id,
        version_no=version_no,
        status="draft",
        fingerprint=built.fingerprint,
        row_count=len(built.rows),
        object_key=object_key,
        source_dataset_fingerprint=built.source_dataset_fingerprint,
        label_policy=built.label_policy,
        feature_schema=built.feature_schema,
        split_manifest=built.split_manifest,
        quality_report=built.quality_report,
        engine_versions=built.engine_versions,
        created_by=owner_user_id,
    )
    session.add(version)
    await session.commit()
    loaded = await get_training_version(session, version.id)
    assert loaded is not None
    return loaded[1]


async def publish_training_version(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> TrainingDatasetVersion:
    loaded = await get_training_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Training dataset version not found", retryable=False)
    _dataset, version = loaded
    if version.status != "draft":
        raise AppError("INVALID_STATE", f"Cannot publish status={version.status}", retryable=False)
    # Traceability gate
    trace = (version.quality_report or {}).get("traceability", {})
    if not all(
        [
            trace.get("all_rows_have_source_timestamp"),
            trace.get("all_rows_have_strategy_version"),
            trace.get("all_rows_have_label_policy"),
        ]
    ):
        raise AppError("QUALITY_GATE", "Traceability checks failed", retryable=False)
    version.status = "published"
    version.published_at = datetime.now(UTC)
    _ = actor_user_id
    await session.commit()
    loaded2 = await get_training_version(session, version.id)
    assert loaded2 is not None
    return loaded2[1]


async def list_training_datasets(session: AsyncSession) -> list[TrainingDataset]:
    result = await session.execute(
        select(TrainingDataset).order_by(TrainingDataset.created_at.desc())
    )
    return list(result.scalars().all())


def preview_rows_from_object(object_key: str, *, limit: int = 5) -> list[dict[str, Any]]:
    import json

    raw = LocalObjectStorage().get_bytes(object_key)
    lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines[:limit]]
