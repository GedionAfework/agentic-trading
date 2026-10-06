from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from private_trading_core.config import get_settings
from pydantic import BaseModel, Field

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
    version: str = "0.1.0"
    checks: dict[str, Any] = Field(default_factory=dict)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness/readiness stub — dependency deep-checks arrive in later phases."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        env=settings.app_env,
        checks={
            "api": "ok",
            "scanner_enabled": settings.scanner_enabled,
            "notifications_enabled": settings.notifications_enabled,
        },
    )
