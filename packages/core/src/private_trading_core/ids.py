from __future__ import annotations

import uuid


def new_id() -> uuid.UUID:
    """Prefer UUIDv7 when available (Python 3.13+), else UUIDv4."""
    if hasattr(uuid, "uuid7"):
        return uuid.uuid7()  # type: ignore[attr-defined]
    return uuid.uuid4()


def new_correlation_id() -> str:
    return str(new_id())
