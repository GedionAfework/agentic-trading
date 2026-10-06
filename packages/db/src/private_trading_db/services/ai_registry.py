from __future__ import annotations

import hashlib

from private_trading_core.config import Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_db.models.ai import ModelRegistry, PromptVersion

SMOKE_PROMPT_KEY = "ai.smoke.structured_v1"
SMOKE_PROMPT_TEMPLATE = (
    "You are a private trading copilot smoke test. "
    "Return JSON only with fields: ok (bool), echo (string), notes (string)."
)


async def ensure_default_ai_registry(session: AsyncSession, settings: Settings) -> None:
    await _ensure_model(
        session,
        name=settings.main_model,
        modality="text",
        endpoint=settings.ollama_base_url,
        family="qwen",
    )
    await _ensure_model(
        session,
        name=settings.embedding_model,
        modality="embedding",
        endpoint=settings.ollama_base_url,
        family="nomic",
    )
    await _ensure_prompt(session, key=SMOKE_PROMPT_KEY, template=SMOKE_PROMPT_TEMPLATE)
    await session.commit()


async def _ensure_model(
    session: AsyncSession,
    *,
    name: str,
    modality: str,
    endpoint: str,
    family: str | None,
) -> None:
    result = await session.execute(
        select(ModelRegistry).where(
            ModelRegistry.name == name,
            ModelRegistry.version_label == "default",
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    session.add(
        ModelRegistry(
            name=name,
            version_label="default",
            family=family,
            modality=modality,
            serving_endpoint=endpoint,
            is_active=True,
        )
    )


async def _ensure_prompt(session: AsyncSession, *, key: str, template: str) -> None:
    result = await session.execute(
        select(PromptVersion).where(PromptVersion.key == key, PromptVersion.version == 1)
    )
    if result.scalar_one_or_none() is not None:
        return
    session.add(
        PromptVersion(
            key=key,
            version=1,
            template=template,
            content_hash=hashlib.sha256(template.encode("utf-8")).hexdigest(),
            is_active=True,
        )
    )


async def get_active_prompt(session: AsyncSession, key: str) -> PromptVersion | None:
    result = await session.execute(
        select(PromptVersion)
        .where(PromptVersion.key == key, PromptVersion.is_active.is_(True))
        .order_by(PromptVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
