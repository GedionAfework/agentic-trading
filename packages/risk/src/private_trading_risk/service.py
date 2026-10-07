from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.risk import RiskAssessment, RiskPolicy, RiskPolicyVersion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import RISK_ENGINE_VERSION, default_policy_config
from private_trading_risk.types import (
    Direction,
    InstrumentRiskMeta,
    RiskAssessmentResult,
    RiskInput,
)


async def get_policy_by_code(session: AsyncSession, code: str) -> RiskPolicy | None:
    result = await session.execute(
        select(RiskPolicy)
        .options(selectinload(RiskPolicy.versions))
        .where(RiskPolicy.code == code)
    )
    return result.scalar_one_or_none()


async def get_policy_version(
    session: AsyncSession, version_id: uuid.UUID
) -> tuple[RiskPolicy, RiskPolicyVersion] | None:
    result = await session.execute(
        select(RiskPolicyVersion)
        .options(
            selectinload(RiskPolicyVersion.policy).selectinload(RiskPolicy.versions),
        )
        .where(RiskPolicyVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return None
    return version.policy, version


async def list_policies(session: AsyncSession) -> list[RiskPolicy]:
    result = await session.execute(select(RiskPolicy).order_by(RiskPolicy.created_at.desc()))
    return list(result.scalars().all())


async def ensure_default_policy(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
) -> RiskPolicyVersion:
    existing = await get_policy_by_code(session, "default-crypto")
    config = default_policy_config()
    if existing is None:
        policy = RiskPolicy(
            owner_user_id=owner_user_id,
            code="default-crypto",
            name="Default crypto paper risk policy",
            description="Engineering-candidate limits pending D-01 lock",
            status="active",
        )
        session.add(policy)
        await session.flush()
        version = RiskPolicyVersion(
            policy_id=policy.id,
            version_no=1,
            status="draft",
            config=config,
            engine_version=RISK_ENGINE_VERSION,
            created_by=owner_user_id,
        )
        session.add(version)
        await session.commit()
        loaded = await get_policy_version(session, version.id)
        assert loaded is not None
        return loaded[1]

    draft = next((v for v in existing.versions if v.status == "draft"), None)
    if draft is not None:
        draft.config = config
        draft.engine_version = RISK_ENGINE_VERSION
        await session.commit()
        loaded = await get_policy_version(session, draft.id)
        assert loaded is not None
        return loaded[1]

    published = next(
        (v for v in sorted(existing.versions, key=lambda x: x.version_no, reverse=True) if v.status == "published"),
        sorted(existing.versions, key=lambda x: x.version_no)[-1],
    )
    loaded = await get_policy_version(session, published.id)
    assert loaded is not None
    return loaded[1]


async def publish_policy_version(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> RiskPolicyVersion:
    loaded = await get_policy_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Risk policy version not found", retryable=False)
    policy, version = loaded
    if version.status != "draft":
        raise AppError("INVALID_STATE", f"Cannot publish status={version.status}", retryable=False)
    for other in policy.versions:
        if other.id != version.id and other.status == "published":
            other.status = "retired"
    version.status = "published"
    version.published_at = datetime.now(UTC)
    _ = actor_user_id
    await session.commit()
    loaded2 = await get_policy_version(session, version.id)
    assert loaded2 is not None
    return loaded2[1]


def _parse_input(body: dict[str, Any]) -> RiskInput:
    instrument = None
    raw_inst = body.get("instrument")
    if isinstance(raw_inst, dict):
        instrument = InstrumentRiskMeta(
            asset_class=str(raw_inst.get("asset_class", "crypto")),
            price_tick=_opt_dec(raw_inst.get("price_tick")),
            qty_step=_opt_dec(raw_inst.get("qty_step")),
            min_notional=_opt_dec(raw_inst.get("min_notional")),
            pip_size=_opt_dec(raw_inst.get("pip_size")),
            lot_size=_opt_dec(raw_inst.get("lot_size")),
        )
    return RiskInput(
        direction=Direction(str(body["direction"])),
        entry=_opt_dec(body.get("entry")),
        stop=_opt_dec(body.get("stop")),
        target_1=_opt_dec(body.get("target_1")),
        data_fresh=bool(body.get("data_fresh", True)),
        market_actionable=bool(body.get("market_actionable", True)),
        is_weekend=bool(body.get("is_weekend", False)),
        in_event_blackout=bool(body.get("in_event_blackout", False)),
        account_equity=_opt_dec(body.get("account_equity")),
        open_risk_pct=_opt_dec(body.get("open_risk_pct")),
        summary_text=body.get("summary_text"),
        instrument=instrument,
        setup_id=str(body["setup_id"]) if body.get("setup_id") else None,
    )


def _opt_dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


async def evaluate_and_persist(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    payload: dict[str, Any],
) -> tuple[RiskAssessmentResult, RiskAssessment]:
    loaded = await get_policy_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Risk policy version not found", retryable=False)
    policy, version = loaded
    risk_input = _parse_input(payload)
    result = assess_risk(
        policy_code=policy.code,
        policy_version_no=version.version_no,
        policy_config=dict(version.config or {}),
        risk_input=risk_input,
    )
    setup_uuid = uuid.UUID(risk_input.setup_id) if risk_input.setup_id else None
    row = RiskAssessment(
        policy_version_id=version.id,
        setup_id=setup_uuid,
        direction=result.direction.value,
        entry_reference=result.entry_reference,
        stop_price=result.stop_price,
        target_1=result.target_1,
        risk_distance=result.risk_distance,
        reward_distance=result.reward_distance,
        rr_ratio=result.rr_ratio,
        hard_blockers=list(result.hard_blockers),
        warnings=list(result.warnings),
        approved=result.approved,
        paper_size={
            "risk_pct": str(result.paper_size.risk_pct) if result.paper_size else None,
            "risk_amount": str(result.paper_size.risk_amount)
            if result.paper_size and result.paper_size.risk_amount is not None
            else None,
            "quantity": str(result.paper_size.quantity)
            if result.paper_size and result.paper_size.quantity is not None
            else None,
            "notional": str(result.paper_size.notional)
            if result.paper_size and result.paper_size.notional is not None
            else None,
            "notes": result.paper_size.notes if result.paper_size else [],
        },
        input_snapshot=payload,
        engine_version=result.engine_version,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return result, row
