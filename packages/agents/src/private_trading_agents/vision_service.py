from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.vision import ScreenshotJob
from private_trading_knowledge.storage import LocalObjectStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_agents.vision import (
    RETENTION_DAYS,
    VisionVerdict,
    parse_vlm_payload,
    validate_image,
    verify_read,
)


async def analyze_screenshot(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    market_symbol: str | None = None,
    market_timeframe: str | None = None,
    vlm_payload: dict[str, Any] | None = None,
) -> ScreenshotJob:
    detected = validate_image(data, content_type)
    suffix = { "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp" }[detected]
    object_key, digest = LocalObjectStorage().put_bytes(data, suffix=suffix)
    read = parse_vlm_payload(vlm_payload)
    verdict = verify_read(read, market_symbol=market_symbol, market_timeframe=market_timeframe)
    status = "needs_clarification" if verdict.needs_clarification else "analyzed"
    job = ScreenshotJob(
        owner_user_id=owner_user_id,
        object_key=object_key,
        content_sha256=digest,
        content_type=detected,
        byte_size=len(data),
        status=status,
        market_symbol=market_symbol.upper() if market_symbol else None,
        market_timeframe=market_timeframe.lower() if market_timeframe else None,
        extraction=read.to_dict(),
        verification=verdict.to_dict(),
        authorizes_trade=False,
        retain_until=datetime.now(UTC) + timedelta(days=RETENTION_DAYS),
    )
    session.add(job)
    await session.commit()
    return job


async def get_screenshot_job(session: AsyncSession, job_id: uuid.UUID) -> ScreenshotJob | None:
    result = await session.execute(select(ScreenshotJob).where(ScreenshotJob.id == job_id))
    return result.scalar_one_or_none()


async def correct_screenshot(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    symbol: str,
    timeframe: str,
) -> ScreenshotJob:
    job = await get_screenshot_job(session, job_id)
    if job is None:
        raise AppError("NOT_FOUND", "Screenshot job not found", retryable=False)
    job.corrected_symbol = symbol.upper()
    job.corrected_timeframe = timeframe.lower()
    job.corrected_by = actor_user_id
    job.corrected_at = datetime.now(UTC)
    job.status = "corrected"
    job.authorizes_trade = False
    verification = dict(job.verification or {})
    verification["user_correction"] = {
        "symbol": job.corrected_symbol,
        "timeframe": job.corrected_timeframe,
    }
    verification["authorizes_trade"] = False
    job.verification = verification
    await session.commit()
    loaded = await get_screenshot_job(session, job.id)
    assert loaded is not None
    return loaded


def verdict_from_job(job: ScreenshotJob) -> VisionVerdict:
    payload = dict(job.verification or {})
    return VisionVerdict(
        status=str(payload.get("status") or "clarification_required"),
        consistent=bool(payload.get("consistent")),
        needs_clarification=bool(payload.get("needs_clarification", True)),
        authorizes_trade=False,
        blocker=payload.get("blocker"),
    )
