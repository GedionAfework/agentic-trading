from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from private_trading_core.errors import NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_decision.service import (
    build_and_register,
    get_training_dataset_by_code,
    get_training_version,
    list_training_datasets,
    preview_rows_from_object,
    publish_training_version,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.training import (
    BuildTrainingRequest,
    BuildTrainingResponse,
    TrainingDatasetOut,
    TrainingVersionOut,
)

router = APIRouter(prefix="/training", tags=["training"])


def _dataset_out(d) -> TrainingDatasetOut:
    return TrainingDatasetOut(
        id=d.id,
        code=d.code,
        name=d.name,
        description=d.description,
        status=d.status,
        created_at=d.created_at,
    )


def _version_out(v) -> TrainingVersionOut:
    return TrainingVersionOut(
        id=v.id,
        dataset_id=v.dataset_id,
        version_no=v.version_no,
        status=v.status,
        fingerprint=v.fingerprint,
        row_count=v.row_count,
        object_key=v.object_key,
        source_dataset_fingerprint=v.source_dataset_fingerprint,
        label_policy=dict(v.label_policy or {}),
        feature_schema=dict(v.feature_schema or {}),
        split_manifest=dict(v.split_manifest or {}),
        quality_report=dict(v.quality_report or {}),
        engine_versions=dict(v.engine_versions or {}),
        created_at=v.created_at,
        published_at=v.published_at,
    )


@router.get("/datasets", response_model=list[TrainingDatasetOut])
async def get_datasets(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TrainingDatasetOut]:
    user.require_roles("owner", "admin", "viewer")
    return [_dataset_out(d) for d in await list_training_datasets(session)]


@router.post("/datasets/build", response_model=BuildTrainingResponse)
async def post_build(
    body: BuildTrainingRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BuildTrainingResponse:
    user.require_roles("owner", "admin")
    version = await build_and_register(
        session,
        owner_user_id=user.id,
        code=body.code,
        name=body.name,
        backtest_dataset_id=body.backtest_dataset_id,
        use_frozen_fixture=body.use_frozen_fixture,
        split_mode=body.split_mode,
    )
    dataset = await get_training_dataset_by_code(session, body.code)
    assert dataset is not None
    preview: list[dict] = []
    if version.object_key:
        preview = preview_rows_from_object(version.object_key, limit=3)
    await record_audit(
        session,
        action="training.dataset_built",
        actor_type="user",
        actor_id=user.id,
        resource_type="training_dataset_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
        metadata={
            "fingerprint": version.fingerprint,
            "row_count": version.row_count,
            "split_mode": body.split_mode,
        },
    )
    await session.commit()
    return BuildTrainingResponse(
        dataset=_dataset_out(dataset),
        version=_version_out(version),
        preview_rows=preview,
    )


@router.get("/datasets/versions/{version_id}", response_model=TrainingVersionOut)
async def get_version(
    version_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingVersionOut:
    user.require_roles("owner", "admin", "viewer")
    loaded = await get_training_version(session, version_id)
    if loaded is None:
        raise NotFoundError("Training dataset version not found")
    return _version_out(loaded[1])


@router.post("/datasets/versions/{version_id}/publish", response_model=TrainingVersionOut)
async def post_publish(
    version_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingVersionOut:
    user.require_roles("owner", "admin")
    version = await publish_training_version(
        session, version_id=version_id, actor_user_id=user.id
    )
    await record_audit(
        session,
        action="training.dataset_published",
        actor_type="user",
        actor_id=user.id,
        resource_type="training_dataset_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return _version_out(version)
