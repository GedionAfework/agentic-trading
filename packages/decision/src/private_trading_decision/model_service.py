from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from private_trading_core.errors import AppError
from private_trading_db.models.decision_model import DecisionModel
from private_trading_db.models.training import TrainingDatasetVersion
from private_trading_knowledge.storage import LocalObjectStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_decision.matrix import DECISION_MODEL_VERSION, rows_from_jsonl
from private_trading_decision.predict import LoadedModel, RankDecision
from private_trading_decision.train import TrainedCandidate, train_baseline_and_challenger
from private_trading_decision.types import TrainingRow


def _artifact_bytes(candidate: TrainedCandidate) -> bytes:
    return json.dumps(candidate.artifact, sort_keys=True).encode("utf-8")


async def _persist_candidate(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    code: str,
    name: str,
    candidate: TrainedCandidate,
    training_version_id: uuid.UUID | None,
) -> DecisionModel:
    existing = await session.execute(
        select(DecisionModel).where(DecisionModel.fingerprint == candidate.fingerprint)
    )
    prior = existing.scalar_one_or_none()
    if prior is not None:
        return prior
    key, _sha = LocalObjectStorage().put_bytes(_artifact_bytes(candidate), suffix=".json")
    row = DecisionModel(
        owner_user_id=owner_user_id,
        code=code,
        name=name,
        algorithm=candidate.algorithm,
        role=candidate.role,
        mode="shadow",
        status="trained",
        fingerprint=candidate.fingerprint,
        object_key=key,
        training_dataset_version_id=training_version_id,
        feature_schema=candidate.feature_schema,
        training_window=candidate.training_window,
        metrics=candidate.metrics,
        feature_importance=candidate.feature_importance,
        hyperparameters=candidate.params,
        engine_version=DECISION_MODEL_VERSION,
        created_by=owner_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def train_from_rows(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    rows: list[TrainingRow],
    code: str,
    name: str,
    training_version_id: uuid.UUID | None,
) -> tuple[DecisionModel, DecisionModel, str]:
    trained = train_baseline_and_challenger(rows)
    baseline = await _persist_candidate(
        session,
        owner_user_id=owner_user_id,
        code=code,
        name=f"{name} baseline",
        candidate=trained.baseline,
        training_version_id=training_version_id,
    )
    challenger = await _persist_candidate(
        session,
        owner_user_id=owner_user_id,
        code=code,
        name=f"{name} challenger",
        candidate=trained.challenger,
        training_version_id=training_version_id,
    )
    await session.commit()
    return baseline, challenger, trained.recommended_role


async def train_registered_dataset(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    training_version_id: uuid.UUID,
    code: str = "decision-lgbm-v1",
    name: str = "Decision ranker v1",
) -> tuple[DecisionModel, DecisionModel, str]:
    result = await session.execute(
        select(TrainingDatasetVersion).where(TrainingDatasetVersion.id == training_version_id)
    )
    version = result.scalar_one_or_none()
    if version is None or not version.object_key:
        raise AppError("NOT_FOUND", "Training dataset version not found", retryable=False)
    if version.status != "published":
        raise AppError(
            "INVALID_STATE",
            "Train only from a published dataset version",
            retryable=False,
        )
    rows = rows_from_jsonl(LocalObjectStorage().get_bytes(version.object_key))
    return await train_from_rows(
        session,
        owner_user_id=owner_user_id,
        rows=rows,
        code=code,
        name=name,
        training_version_id=version.id,
    )


async def list_decision_models(session: AsyncSession) -> list[DecisionModel]:
    result = await session.execute(select(DecisionModel).order_by(DecisionModel.created_at.desc()))
    return list(result.scalars().all())


async def get_decision_model(session: AsyncSession, model_id: uuid.UUID) -> DecisionModel | None:
    result = await session.execute(select(DecisionModel).where(DecisionModel.id == model_id))
    return result.scalar_one_or_none()


async def promote_decision_model(
    session: AsyncSession,
    *,
    model_id: uuid.UUID,
) -> DecisionModel:
    model = await get_decision_model(session, model_id)
    if model is None:
        raise AppError("NOT_FOUND", "Decision model not found", retryable=False)
    if model.status == "retired":
        raise AppError("INVALID_STATE", "Retired models cannot be promoted", retryable=False)
    current = await session.execute(
        select(DecisionModel).where(
            DecisionModel.code == model.code,
            DecisionModel.mode == "champion",
            DecisionModel.status == "promoted",
        )
    )
    for prior in current.scalars().all():
        if prior.id == model.id:
            continue
        prior.mode = "shadow"
        prior.status = "retired"
        prior.role = "challenger" if prior.role == "champion" else prior.role
    model.mode = "champion"
    model.role = "champion"
    model.status = "promoted"
    model.promoted_at = datetime.now(UTC)
    await session.commit()
    loaded = await get_decision_model(session, model.id)
    assert loaded is not None
    return loaded


def load_model_artifact(model: DecisionModel) -> LoadedModel:
    if not model.object_key:
        raise AppError("INVALID_STATE", "Decision model has no artifact", retryable=False)
    raw = LocalObjectStorage().get_bytes(model.object_key)
    return LoadedModel(json.loads(raw.decode("utf-8")))


def predict_with_model(
    model: DecisionModel,
    features: dict,
    *,
    strategy_ready: bool,
    risk_approved: bool,
    hard_blockers: list[str] | None = None,
) -> RankDecision:
    loaded = load_model_artifact(model)
    return loaded.decide(
        features,
        strategy_ready=strategy_ready,
        risk_approved=risk_approved,
        hard_blockers=hard_blockers,
        mode=model.mode,
    )
