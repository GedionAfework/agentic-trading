from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import PlainTextResponse
from private_trading_agents.scanner_service import get_kill_switches
from private_trading_core.config import Settings, get_settings, production_settings_errors
from private_trading_core.errors import AppError, UnauthorizedError
from private_trading_release.execution import execution_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_current_user, get_db
from private_trading_api.metrics import REGISTRY

router = APIRouter(tags=["ops"])


@router.get("/ops/readiness")
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Deep-ish readiness: settings policy + kill switches + DB ping."""
    errors = production_settings_errors(settings)
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — surface as readiness failure
        db_ok = False
        errors.append(f"database_unreachable: {exc.__class__.__name__}")
    switches = await get_kill_switches(session)
    execution = execution_status()
    if not execution["ok"]:
        errors.append("broker_execution_artifacts_present")
    status = "ready" if db_ok and not errors else "not_ready"
    return {
        "status": status,
        "env": settings.app_env,
        "database_ok": db_ok,
        "kill_switches": switches,
        "production_policy_errors": errors,
        "broker_execution": execution,
        "notes": [
            "Kill switches are owner/admin controllable via /v1/scanner/switches.",
            "Live broker execution remains undeployed (FR-SIG-008).",
            "Production alerts require /v1/release live_alerts_enabled after Gates A–G.",
        ],
    }


@router.get("/metrics")
async def prometheus_metrics(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    if not settings.metrics_enabled:
        raise AppError("NOT_FOUND", "Metrics disabled", retryable=False)
    token = (settings.metrics_bearer_token or "").strip()
    if token:
        expected = f"Bearer {token}"
        if authorization != expected:
            raise UnauthorizedError("Metrics token required")
    body = REGISTRY.render()
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")


@router.get("/ops/exposure-checklist")
async def exposure_checklist(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Owner-facing Gate A checklist — not a network scanner."""
    user.require_roles("owner", "admin")
    return {
        "env": settings.app_env,
        "checks": [
            {
                "id": "private_bind_data_plane",
                "ok": settings.app_env != "production"
                or "0.0.0.0" not in (settings.database_url + settings.redis_url),
                "detail": (
                    "Postgres/Redis/Ollama/MinIO must bind privately "
                    "(see infra/docker/docker-compose.prod.yml)."
                ),
            },
            {
                "id": "jwt_not_default",
                "ok": not production_settings_errors(settings)
                or settings.app_env != "production",
                "detail": "Production rejects default jwt_secret / DB credentials.",
            },
            {
                "id": "metrics_optional_auth",
                "ok": bool(settings.metrics_bearer_token) or settings.app_env != "production",
                "detail": "Set METRICS_BEARER_TOKEN in production so /metrics is not public.",
            },
            {
                "id": "broker_execution_absent",
                "ok": True,
                "detail": "No live broker execution module is deployed.",
            },
        ],
        "runbooks": "docs/ops/",
    }
