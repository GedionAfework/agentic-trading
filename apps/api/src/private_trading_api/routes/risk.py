from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from private_trading_core.errors import NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_risk.service import (
    ensure_default_policy,
    evaluate_and_persist,
    get_policy_by_code,
    get_policy_version,
    list_policies,
    publish_policy_version,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.risk import (
    AssessRiskRequest,
    EnsureRiskPolicyResponse,
    PaperSizeOut,
    RiskAssessmentOut,
    RiskPolicyOut,
    RiskPolicyVersionOut,
)

router = APIRouter(prefix="/risk", tags=["risk"])


def _policy_out(p) -> RiskPolicyOut:
    return RiskPolicyOut(
        id=p.id,
        code=p.code,
        name=p.name,
        description=p.description,
        status=p.status,
        created_at=p.created_at,
    )


def _version_out(v) -> RiskPolicyVersionOut:
    return RiskPolicyVersionOut(
        id=v.id,
        policy_id=v.policy_id,
        version_no=v.version_no,
        status=v.status,
        engine_version=v.engine_version,
        published_at=v.published_at,
        config=dict(v.config or {}),
    )


@router.get("/policies", response_model=list[RiskPolicyOut])
async def get_policies(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RiskPolicyOut]:
    user.require_roles("owner", "admin", "viewer")
    return [_policy_out(p) for p in await list_policies(session)]


@router.post("/policies/ensure-default", response_model=EnsureRiskPolicyResponse)
async def post_ensure_default(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EnsureRiskPolicyResponse:
    user.require_roles("owner", "admin")
    version = await ensure_default_policy(session, owner_user_id=user.id)
    policy = await get_policy_by_code(session, "default-crypto")
    assert policy is not None
    await record_audit(
        session,
        action="risk.policy_ensure_default",
        actor_type="user",
        actor_id=user.id,
        resource_type="risk_policy_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return EnsureRiskPolicyResponse(policy=_policy_out(policy), version=_version_out(version))


@router.post("/policies/versions/{version_id}/publish", response_model=RiskPolicyVersionOut)
async def post_publish(
    version_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RiskPolicyVersionOut:
    user.require_roles("owner", "admin")
    version = await publish_policy_version(
        session, version_id=version_id, actor_user_id=user.id
    )
    await record_audit(
        session,
        action="risk.policy_published",
        actor_type="user",
        actor_id=user.id,
        resource_type="risk_policy_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return _version_out(version)


@router.post("/policies/versions/{version_id}/assess", response_model=RiskAssessmentOut)
async def post_assess(
    version_id: uuid.UUID,
    body: AssessRiskRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RiskAssessmentOut:
    """Deterministic risk veto. Never places live orders."""
    user.require_roles("owner", "admin", "viewer")
    loaded = await get_policy_version(session, version_id)
    if loaded is None:
        raise NotFoundError("Risk policy version not found")
    result, row = await evaluate_and_persist(
        session, version_id=version_id, payload=body.model_dump(mode="json")
    )
    paper = result.paper_size
    return RiskAssessmentOut(
        id=row.id,
        approved=result.approved,
        direction=result.direction.value,
        entry_reference=result.entry_reference,
        stop_price=result.stop_price,
        target_1=result.target_1,
        risk_distance=result.risk_distance,
        reward_distance=result.reward_distance,
        rr_ratio=result.rr_ratio,
        hard_blockers=result.hard_blockers,
        warnings=result.warnings,
        paper_size=PaperSizeOut(
            risk_pct=str(paper.risk_pct) if paper else None,
            risk_amount=str(paper.risk_amount) if paper and paper.risk_amount is not None else None,
            quantity=str(paper.quantity) if paper and paper.quantity is not None else None,
            notional=str(paper.notional) if paper and paper.notional is not None else None,
            notes=paper.notes if paper else [],
        ),
        engine_version=result.engine_version,
        policy_code=result.policy_code,
        policy_version_no=result.policy_version_no,
        meta=result.meta,
    )
