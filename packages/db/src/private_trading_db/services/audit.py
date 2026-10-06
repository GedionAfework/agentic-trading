from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_db.models.ops import AuditEvent


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_type: str = "user",
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        metadata_=metadata or {},
    )
    session.add(event)
    return event
