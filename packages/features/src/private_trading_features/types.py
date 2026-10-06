from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class TriState(StrEnum):
    """Boolean-like feature outcome with fail-closed UNKNOWN."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class CandleBar:
    """Pure OHLCV bar — no provider JSON, no DB coupling."""

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    is_final: bool = True


@dataclass(slots=True, frozen=True)
class FeatureValue:
    name: str
    version: str
    status: TriState
    value: Any = None
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.status != TriState.UNKNOWN

    @classmethod
    def unknown(cls, name: str, version: str, reason: str, **meta: Any) -> FeatureValue:
        return cls(name=name, version=version, status=TriState.UNKNOWN, reason=reason, meta=meta)

    @classmethod
    def of(
        cls,
        name: str,
        version: str,
        *,
        status: TriState,
        value: Any = None,
        reason: str | None = None,
        **meta: Any,
    ) -> FeatureValue:
        return cls(
            name=name,
            version=version,
            status=status,
            value=value,
            reason=reason,
            meta=meta,
        )


@dataclass(slots=True, frozen=True)
class FeatureSnapshot:
    """Evidence bundle for a single evaluation point (optional persistence later)."""

    as_of: datetime
    bar_index: int
    feature_engine_version: str
    values: dict[str, FeatureValue]
    cache_key: str
