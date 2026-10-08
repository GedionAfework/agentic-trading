from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.analytics import RetrainRequest
from private_trading_db.models.decision_model import DecisionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# P&L panic alone is never sufficient to approve a retrain.
BLOCKED_SOLE_REASONS = frozenset({"pnl_panic", "paper_drawdown_panic", "equity_panic"})
REQUIRED_EVAL_KEYS = frozenset({"holdout_metrics", "comparison_notes"})


async def list_model_governance(session: AsyncSession) -> list[dict[str, Any]]:
    result = await session.execute(select(DecisionModel).order_by(DecisionModel.created_at.desc()))
    out: list[dict[str, Any]] = []
    for model in result.scalars().all():
        out.append(
            {
                "id": str(model.id),
                "code": model.code,
                "name": model.name,
                "algorithm": model.algorithm,
                "role": model.role,
                "mode": model.mode,
                "status": model.status,
                "metrics": dict(model.metrics or {}),
                "promoted_at": model.promoted_at.isoformat() if model.promoted_at else None,
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "note": (
                    "Shadow until explicit promote. Drift flags never auto-promote "
                    "or auto-retrain."
                ),
            }
        )
    return out


def _validate_approval_payload(
    *,
    reason_codes: list[str],
    evaluation: dict[str, Any],
) -> None:
    codes = {c.strip() for c in reason_codes if c and str(c).strip()}
    if not codes:
        raise AppError(
            "INVALID_INPUT",
            "Approval requires non-empty reason_codes beyond vibes",
            retryable=False,
        )
    if codes <= BLOCKED_SOLE_REASONS:
        raise AppError(
            "POLICY_VIOLATION",
            "Retrain cannot be approved for P&L panic alone; attach evaluation evidence",
            retryable=False,
        )
    missing = REQUIRED_EVAL_KEYS - set(evaluation.keys())
    if missing:
        raise AppError(
            "INVALID_INPUT",
            f"evaluation missing required keys: {sorted(missing)}",
            retryable=False,
        )
    holdout = evaluation.get("holdout_metrics")
    if not isinstance(holdout, dict) or not holdout:
        raise AppError(
            "INVALID_INPUT",
            "evaluation.holdout_metrics must be a non-empty object of computed metrics",
            retryable=False,
        )


async def create_retrain_request(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    decision_model_code: str,
    reason: str,
    reason_codes: list[str],
    evaluation: dict[str, Any] | None = None,
) -> RetrainRequest:
    row = RetrainRequest(
        owner_user_id=owner_user_id,
        decision_model_code=decision_model_code,
        reason=reason,
        reason_codes=list(reason_codes),
        evaluation=dict(evaluation or {}),
        status="pending",
    )
    session.add(row)
    await session.flush()
    return row


async def list_retrain_requests(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[RetrainRequest]:
    result = await session.execute(
        select(RetrainRequest)
        .where(RetrainRequest.owner_user_id == owner_user_id)
        .order_by(RetrainRequest.created_at.desc())
    )
    return list(result.scalars().all())


async def approve_retrain_request(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    approver_id: uuid.UUID,
    reason_codes: list[str] | None = None,
    evaluation: dict[str, Any] | None = None,
) -> RetrainRequest:
    result = await session.execute(
        select(RetrainRequest).where(
            RetrainRequest.id == request_id,
            RetrainRequest.owner_user_id == owner_user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "Retrain request not found", retryable=False)
    if row.status != "pending":
        raise AppError("INVALID_STATE", f"Request is {row.status}, not pending", retryable=False)

    codes = list(reason_codes) if reason_codes is not None else list(row.reason_codes or [])
    eval_payload = dict(evaluation) if evaluation is not None else dict(row.evaluation or {})
    _validate_approval_payload(reason_codes=codes, evaluation=eval_payload)
    row.reason_codes = codes
    row.evaluation = eval_payload
    row.status = "approved"
    row.approved_by = approver_id
    row.approved_at = datetime.now(UTC)
    await session.flush()
    return row


async def reject_retrain_request(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    rejection_reason: str,
) -> RetrainRequest:
    result = await session.execute(
        select(RetrainRequest).where(
            RetrainRequest.id == request_id,
            RetrainRequest.owner_user_id == owner_user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "Retrain request not found", retryable=False)
    if row.status != "pending":
        raise AppError("INVALID_STATE", f"Request is {row.status}, not pending", retryable=False)
    row.status = "rejected"
    row.rejection_reason = rejection_reason
    await session.flush()
    return row


def retrain_to_dict(row: RetrainRequest) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "decision_model_code": row.decision_model_code,
        "reason": row.reason,
        "reason_codes": list(row.reason_codes or []),
        "evaluation": dict(row.evaluation or {}),
        "status": row.status,
        "rejection_reason": row.rejection_reason,
        "approved_by": None if row.approved_by is None else str(row.approved_by),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        "resulting_model_ids": list(row.resulting_model_ids or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "policy": "P&L panic alone cannot approve; holdout_metrics required.",
    }
