from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.ops import SystemSetting
from private_trading_db.models.release import ReleaseSignoff, ReleaseWaiver
from private_trading_paper_trade.service import get_account, integrity_report, soak_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_release.execution import execution_status
from private_trading_release.policy import (
    REQUIRED_GATES,
    ReleasePolicy,
    evaluate_alert_gate,
)

POLICY_KEY = "live_alert_release"


async def get_policy(session: AsyncSession) -> ReleasePolicy:
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == POLICY_KEY))
    row = result.scalar_one_or_none()
    return ReleasePolicy.from_dict(None if row is None else dict(row.value or {}))


async def save_policy(
    session: AsyncSession,
    *,
    policy: ReleasePolicy,
    actor_user_id: uuid.UUID,
) -> ReleasePolicy:
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == POLICY_KEY))
    row = result.scalar_one_or_none()
    payload = policy.to_dict()
    if row is None:
        row = SystemSetting(key=POLICY_KEY, value=payload, updated_by=actor_user_id)
        session.add(row)
    else:
        row.value = payload
        row.updated_by = actor_user_id
    await session.flush()
    return policy


async def list_signoffs(session: AsyncSession) -> list[ReleaseSignoff]:
    result = await session.execute(select(ReleaseSignoff).order_by(ReleaseSignoff.gate))
    return list(result.scalars().all())


async def sign_gate(
    session: AsyncSession,
    *,
    gate: str,
    signer_id: uuid.UUID,
    notes: str | None,
    evidence: dict[str, Any] | None = None,
) -> ReleaseSignoff:
    gate = gate.strip().upper()
    if gate not in REQUIRED_GATES:
        raise AppError("INVALID_INPUT", f"gate must be one of {REQUIRED_GATES}", retryable=False)
    existing = await session.execute(select(ReleaseSignoff).where(ReleaseSignoff.gate == gate))
    row = existing.scalar_one_or_none()
    if row is None:
        row = ReleaseSignoff(
            gate=gate,
            signed_by=signer_id,
            notes=notes,
            evidence=dict(evidence or {}),
        )
        session.add(row)
    else:
        row.signed_by = signer_id
        row.notes = notes
        row.evidence = dict(evidence or {})
        row.signed_at = datetime.now(UTC)
    await session.flush()
    return row


async def checklist_status(session: AsyncSession) -> dict[str, Any]:
    rows = await list_signoffs(session)
    signed = {r.gate: r for r in rows}
    missing = [g for g in REQUIRED_GATES if g not in signed]
    return {
        "required_gates": list(REQUIRED_GATES),
        "signed": {
            g: {
                "signed_by": str(signed[g].signed_by),
                "signed_at": signed[g].signed_at.isoformat(),
                "notes": signed[g].notes,
            }
            for g in REQUIRED_GATES
            if g in signed
        },
        "missing": missing,
        "complete": not missing,
    }


async def list_waivers(
    session: AsyncSession, *, active_only: bool = True
) -> list[ReleaseWaiver]:
    stmt = select(ReleaseWaiver).order_by(ReleaseWaiver.created_at.desc())
    if active_only:
        stmt = stmt.where(ReleaseWaiver.active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_waiver(
    session: AsyncSession,
    *,
    code: str,
    requirement: str,
    reason: str,
    approver_id: uuid.UUID,
    expires_at: datetime | None = None,
) -> ReleaseWaiver:
    code = code.strip()
    if not code or not reason.strip():
        raise AppError("INVALID_INPUT", "waiver code and reason required", retryable=False)
    row = ReleaseWaiver(
        code=code,
        requirement=requirement,
        reason=reason,
        approved_by=approver_id,
        expires_at=expires_at,
        active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def revoke_waiver(
    session: AsyncSession, *, waiver_id: uuid.UUID, actor_user_id: uuid.UUID
) -> ReleaseWaiver:
    result = await session.execute(select(ReleaseWaiver).where(ReleaseWaiver.id == waiver_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "Waiver not found", retryable=False)
    row.active = False
    row.revoked_at = datetime.now(UTC)
    await session.flush()
    _ = actor_user_id
    return row


async def active_waiver_codes(session: AsyncSession, *, now: datetime | None = None) -> set[str]:
    current = now or datetime.now(UTC)
    codes: set[str] = set()
    for row in await list_waivers(session, active_only=True):
        if row.expires_at is not None and row.expires_at <= current:
            continue
        codes.add(row.code)
    return codes


async def paper_gate_facts(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    """Read-only Gate F facts — no commit (safe inside scanner transactions)."""
    account = await get_account(session, owner_user_id=owner_user_id)
    if account is None:
        soak = {
            "started": False,
            "days_elapsed": 0,
            "days_required": 14,
            "complete": False,
        }
        integrity: dict[str, Any] = {"ok": True, "defects": []}
    else:
        soak = soak_status(account)
        integrity = await integrity_report(session, account_id=account.id)
    return {
        "soak_complete": bool(soak.get("complete")),
        "integrity_ok": bool(integrity.get("ok", True)),
        "soak": soak,
        "integrity": integrity,
    }


async def evaluate_for_candidate(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    symbol: str,
    timeframe: str,
    action: str,
    confidence_band: str | None,
    risk_approved: bool | None,
    notifications_enabled: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    policy = await get_policy(session)
    checklist = await checklist_status(session)
    paper = await paper_gate_facts(session, owner_user_id=owner_user_id)
    waivers = await active_waiver_codes(session, now=current)
    decision = evaluate_alert_gate(
        policy=policy,
        symbol=symbol,
        timeframe=timeframe,
        action=action,
        confidence_band=confidence_band,
        risk_approved=risk_approved,
        now=current,
        notifications_enabled=notifications_enabled,
        checklist_complete=bool(checklist["complete"]),
        soak_complete=bool(paper["soak_complete"]),
        integrity_ok=bool(paper["integrity_ok"]),
        active_waiver_codes=waivers,
    )
    decision["policy_live_alerts_enabled"] = policy.live_alerts_enabled
    decision["execution"] = execution_status()
    return decision


async def enable_live_alerts(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    enabled: bool,
    force: bool = False,
) -> dict[str, Any]:
    """Flip production alert master switch. Refuses if gates incomplete unless force+waiver."""
    exec_status = execution_status()
    if not exec_status["ok"]:
        raise AppError(
            "POLICY_VIOLATION",
            "Cannot enable live alerts while broker execution artifacts are present",
            retryable=False,
            details=exec_status,
        )
    policy = await get_policy(session)
    if enabled:
        checklist = await checklist_status(session)
        paper = await paper_gate_facts(session, owner_user_id=actor_user_id)
        waivers = await active_waiver_codes(session)
        blockers: list[str] = []
        if (
            policy.require_checklist
            and not checklist["complete"]
            and "gate_checklist_incomplete" not in waivers
        ):
            blockers.append(f"missing_gates:{checklist['missing']}")
        if (
            policy.require_soak
            and not paper["soak_complete"]
            and "gate_f_soak_incomplete" not in waivers
        ):
            blockers.append("soak_incomplete")
        if (
            policy.require_integrity
            and not paper["integrity_ok"]
            and "gate_f_integrity_defects" not in waivers
        ):
            blockers.append("integrity_defects")
        if blockers and not force:
            raise AppError(
                "INVALID_STATE",
                "Cannot enable live alerts until checklist/soak pass or waivers exist",
                retryable=False,
                details={"blockers": blockers},
            )
    policy.live_alerts_enabled = enabled
    await save_policy(session, policy=policy, actor_user_id=actor_user_id)
    return {
        "live_alerts_enabled": enabled,
        "policy": policy.to_dict(),
        "execution": exec_status,
        "forced": force and enabled,
    }


async def release_status(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    policy = await get_policy(session)
    checklist = await checklist_status(session)
    paper = await paper_gate_facts(session, owner_user_id=owner_user_id)
    waivers = [
        {
            "id": str(w.id),
            "code": w.code,
            "requirement": w.requirement,
            "reason": w.reason,
            "expires_at": None if w.expires_at is None else w.expires_at.isoformat(),
        }
        for w in await list_waivers(session, active_only=True)
    ]
    return {
        "policy": policy.to_dict(),
        "checklist": checklist,
        "paper": paper,
        "waivers": waivers,
        "execution": execution_status(),
        "ready_for_live_alerts": bool(
            checklist["complete"]
            and paper["soak_complete"]
            and paper["integrity_ok"]
            and execution_status()["ok"]
        ),
    }
