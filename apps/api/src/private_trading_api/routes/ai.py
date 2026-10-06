from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from private_trading_ai_gateway import AIGateway
from private_trading_ai_gateway.client import AIGatewayError
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import ForbiddenError
from private_trading_db.services.ai_registry import (
    SMOKE_PROMPT_KEY,
    ensure_default_ai_registry,
    get_active_prompt,
)
from private_trading_db.services.audit import record_audit
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.ai import (
    AIHealthResponse,
    SmokeEmbedRequest,
    SmokeEmbedResponse,
    SmokeGenerateRequest,
    SmokeGenerateResponse,
    SmokeStructuredOut,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _require_owner_admin(user: CurrentUser) -> None:
    user.require_roles("owner", "admin")


async def get_ai_gateway(
    settings: Annotated[Settings, Depends(get_settings)],
):
    async with AIGateway(settings) as gateway:
        yield gateway


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> AIHealthResponse:
    _require_owner_admin(user)
    data = await gateway.health()
    return AIHealthResponse(**data)


@router.post("/smoke/generate", response_model=SmokeGenerateResponse)
async def smoke_generate(
    body: SmokeGenerateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> SmokeGenerateResponse:
    _require_owner_admin(user)
    await ensure_default_ai_registry(session, settings)
    prompt = await get_active_prompt(session, SMOKE_PROMPT_KEY)
    if prompt is None:
        raise ForbiddenError("Smoke prompt is not registered")

    messages = [
        {"role": "system", "content": prompt.template},
        {
            "role": "user",
            "content": f'Create a smoke JSON response with echo="{body.echo}" and ok=true.',
        },
    ]
    try:
        result, meta = await gateway.structured_chat(
            messages=messages,
            schema=SmokeStructuredOut,
            model=settings.main_model,
            prompt_version=f"{prompt.key}:v{prompt.version}",
        )
    except AIGatewayError:
        await record_audit(
            session,
            action="ai.smoke_generate_failed",
            actor_type="user",
            actor_id=user.id,
            correlation_id=get_correlation_id(request),
            metadata={"model": settings.main_model},
        )
        await session.commit()
        raise

    await record_audit(
        session,
        action="ai.smoke_generate_succeeded",
        actor_type="user",
        actor_id=user.id,
        correlation_id=get_correlation_id(request),
        metadata={
            "model": meta.get("model"),
            "prompt_version": meta.get("prompt_version"),
            "repaired": meta.get("repaired"),
        },
    )
    await session.commit()
    return SmokeGenerateResponse(result=result, meta=meta)


@router.post("/smoke/embed", response_model=SmokeEmbedResponse)
async def smoke_embed(
    body: SmokeEmbedRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> SmokeEmbedResponse:
    _require_owner_admin(user)
    await ensure_default_ai_registry(session, settings)
    try:
        vector = await gateway.embed(body.text, model=settings.embedding_model)
    except AIGatewayError:
        await record_audit(
            session,
            action="ai.smoke_embed_failed",
            actor_type="user",
            actor_id=user.id,
            correlation_id=get_correlation_id(request),
            metadata={"model": settings.embedding_model},
        )
        await session.commit()
        raise

    await record_audit(
        session,
        action="ai.smoke_embed_succeeded",
        actor_type="user",
        actor_id=user.id,
        correlation_id=get_correlation_id(request),
        metadata={"model": settings.embedding_model, "dimensions": len(vector)},
    )
    await session.commit()
    return SmokeEmbedResponse(
        dimensions=len(vector),
        preview=vector[:8],
        model=settings.embedding_model,
    )
