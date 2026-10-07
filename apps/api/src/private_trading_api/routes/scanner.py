from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from private_trading_agents.scanner_service import (
    get_kill_switches,
    list_candidates,
    scan_all,
    scanner_status,
    set_kill_switch,
)
from private_trading_core.config import Settings, get_settings
from private_trading_db.services.audit import record_audit
from private_trading_market_data.catalog import ensure_binance_catalog
from private_trading_market_data.providers import BinanceSpotProvider
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.scanner import (
    CandidateOut,
    ScannerStatusOut,
    ScanRequest,
    ScanResponse,
    ScanRunOut,
    SwitchesOut,
    SwitchUpdate,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])


def _timeframes(settings: Settings, requested: list[str]) -> tuple[str, ...]:
    if requested:
        return tuple(requested)
    parsed = tuple(tf.strip() for tf in settings.market_default_timeframes.split(",") if tf.strip())
    return parsed or ("15m", "1h")


@router.post("/run", response_model=ScanResponse)
async def post_run(
    body: ScanRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanResponse:
    user.require_roles("owner", "admin")
    await ensure_binance_catalog(session)
    await session.commit()
    runs = await scan_all(
        session,
        timeframes=_timeframes(settings, body.timeframes),
        owner_user_id=user.id,
        symbols=tuple(body.symbols) or None,
    )
    await record_audit(
        session,
        action="scanner.manual_run",
        actor_type="user",
        actor_id=user.id,
        resource_type="scanner",
        correlation_id=get_correlation_id(request),
        metadata={
            "run_count": len(runs),
            "new_candidates": sum(1 for r in runs if r.get("candidate_new")),
        },
    )
    await session.commit()
    return ScanResponse(runs=[ScanRunOut(**r) for r in runs])


@router.get("/status", response_model=ScannerStatusOut)
async def get_status(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScannerStatusOut:
    user.require_roles("owner", "admin", "viewer")
    status = await scanner_status(session, timeframes=_timeframes(settings, []))
    provider = BinanceSpotProvider(
        base_url=settings.binance_base_url, timeout_seconds=settings.market_http_timeout_seconds
    )
    try:
        health = await provider.health()
        provider_out = {
            "provider_code": health.provider_code,
            "ok": health.ok,
            "degraded": health.degraded,
            "latency_ms": health.latency_ms,
            "message": health.message,
        }
    except Exception as exc:  # noqa: BLE001 — degraded provider is a status
        provider_out = {
            "provider_code": provider.code,
            "ok": False,
            "degraded": True,
            "message": str(exc),
        }
    finally:
        await provider.aclose()
    return ScannerStatusOut(
        scanner_version=status["scanner_version"],
        switches=SwitchesOut(**status["switches"]),
        timeframes=status["timeframes"],
        queues=status["queues"],
        last_run=status["last_run"],
        last_success=status["last_success"],
        dead_letters=status["dead_letters"],
        candidates_total=status["candidates_total"],
        candidates_published=status["candidates_published"],
        provider=provider_out,
    )


@router.get("/switches", response_model=SwitchesOut)
async def get_switches(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SwitchesOut:
    user.require_roles("owner", "admin", "viewer")
    return SwitchesOut(**await get_kill_switches(session))


@router.put("/switches", response_model=SwitchesOut)
async def put_switches(
    body: SwitchUpdate,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SwitchesOut:
    user.require_roles("owner", "admin")
    current = await get_kill_switches(session)
    for key in ("scanner_enabled", "notifications_enabled"):
        value = getattr(body, key)
        if value is not None:
            current = await set_kill_switch(session, key=key, enabled=value, actor_user_id=user.id)
    await record_audit(
        session,
        action="scanner.switches_updated",
        actor_type="user",
        actor_id=user.id,
        resource_type="scanner",
        correlation_id=get_correlation_id(request),
        metadata=dict(current),
    )
    await session.commit()
    return SwitchesOut(**current)


@router.get("/candidates", response_model=list[CandidateOut])
async def get_candidates(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CandidateOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_candidates(session, limit=limit)
    return [
        CandidateOut(
            id=c.id,
            dedupe_key=c.dedupe_key,
            strategy_code=c.strategy_code,
            strategy_version_no=c.strategy_version_no,
            instrument_symbol=c.instrument_symbol,
            timeframe=c.timeframe,
            setup_anchor=c.setup_anchor,
            signal_type=c.signal_type,
            action=c.action,
            candle_open_time=c.candle_open_time,
            decision_record_id=c.decision_record_id,
            publish_state=c.publish_state,
            seen_count=c.seen_count,
            payload=dict(c.payload or {}),
            first_seen_at=c.first_seen_at,
            last_seen_at=c.last_seen_at,
        )
        for c in rows
    ]
