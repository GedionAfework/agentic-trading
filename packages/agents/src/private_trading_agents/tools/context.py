"""Opaque tool context — kept separate to avoid import cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolContext:
    """Opaque runtime extras that must not travel through untrusted JSON."""

    model: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)
