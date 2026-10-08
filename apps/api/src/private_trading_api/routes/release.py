from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from private_trading_db.services.audit import record_audit
from private_trading_release.policy import ReleasePolicy
from private_trading_release.service import (
    create_waiver,
    enable_live_alerts,
    get_policy,
    list_waivers,
    release_status,
    revoke_waiver,
    save_policy,
    sign_gate,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.release import (
    LiveAlertsToggle,
    ReleasePolicyOut,
    ReleasePolicyUpdate,
    SignGateRequest,
    WaiverCreate,
)

router = APIRouter(prefix="/release", tags=["release"])


def _policy_out(policy: ReleasePolicy) -> ReleasePolicyOut:
    return ReleasePolicyOut(**policy.to_dict())


@router.get("/status")
async def get_release_status(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin", "viewer")
    return await release_status(session, owner_user_id=user.id)


@router.get("/policy", response_model=ReleasePolicyOut)
async def get_release_policy(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReleasePolicyOut:
    user.require_roles("owner", "admin", "viewer")
    return _policy_out(await get_policy(session))


@router.put("/policy", response_model=ReleasePolicyOut)
async def put_release_policy(
    body: ReleasePolicyUpdate,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReleasePolicyOut:
    user.require_roles("owner", "admin")
    current = await get_policy(session)
    data = current.to_dict()
    for key, value in body.model_dump(exclude_unset=True).items():
        data[key] = value
    # live_alerts_enabled only via /live-alerts toggle
    data["live_alerts_enabled"] = current.live_alerts_enabled
    policy = ReleasePolicy.from_dict(data)
    await save_policy(session, policy=policy, actor_user_id=user.id)
    await record_audit(
        session,
        action="release.policy_updated",
        actor_type="user",
        actor_id=user.id,
        resource_type="release_policy",
        correlation_id=get_correlation_id(request),
        metadata={"approved_symbols": policy.approved_symbols},
    )
    await session.commit()
    return _policy_out(policy)


@router.post("/signoffs")
async def post_signoff(
    body: SignGateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin")
    row = await sign_gate(
        session,
        gate=body.gate,
        signer_id=user.id,
        notes=body.notes,
        evidence=body.evidence,
    )
    await record_audit(
        session,
        action="release.gate_signed",
        actor_type="user",
        actor_id=user.id,
        resource_type="release_signoff",
        resource_id=row.id,
        correlation_id=get_correlation_id(request),
        metadata={"gate": row.gate},
    )
    await session.commit()
    return {
        "gate": row.gate,
        "signed_by": str(row.signed_by),
        "signed_at": row.signed_at.isoformat(),
        "notes": row.notes,
    }


@router.get("/waivers")
async def get_waivers(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_waivers(session, active_only=False)
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "requirement": r.requirement,
            "reason": r.reason,
            "active": r.active,
            "expires_at": None if r.expires_at is None else r.expires_at.isoformat(),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/waivers")
async def post_waiver(
    body: WaiverCreate,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin")
    row = await create_waiver(
        session,
        code=body.code,
        requirement=body.requirement,
        reason=body.reason,
        approver_id=user.id,
        expires_at=body.expires_at,
    )
    await record_audit(
        session,
        action="release.waiver_created",
        actor_type="user",
        actor_id=user.id,
        resource_type="release_waiver",
        resource_id=row.id,
        correlation_id=get_correlation_id(request),
        metadata={"code": row.code},
    )
    await session.commit()
    return {"id": str(row.id), "code": row.code, "active": row.active}


@router.post("/waivers/{waiver_id}/revoke")
async def post_waiver_revoke(
    waiver_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin")
    row = await revoke_waiver(session, waiver_id=waiver_id, actor_user_id=user.id)
    await session.commit()
    return {"id": str(row.id), "active": row.active, "revoked_at": row.revoked_at.isoformat()}


@router.post("/live-alerts")
async def post_live_alerts(
    body: LiveAlertsToggle,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    user.require_roles("owner", "admin")
    result = await enable_live_alerts(
        session, actor_user_id=user.id, enabled=body.enabled, force=body.force
    )
    await record_audit(
        session,
        action="release.live_alerts_toggled",
        actor_type="user",
        actor_id=user.id,
        resource_type="release_policy",
        correlation_id=get_correlation_id(request),
        metadata={"enabled": body.enabled, "forced": body.force},
    )
    await session.commit()
    return result
