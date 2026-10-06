from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from private_trading_features.types import CandleBar, FeatureValue

FeatureFn = Callable[[list[CandleBar], int], FeatureValue]


@dataclass(slots=True, frozen=True)
class FeatureSpec:
    name: str
    version: str
    lookback: int
    description: str
    lock_status: str  # locked | engineering_candidate | advisory_only
    definition_id: str | None = None
    dependencies: tuple[str, ...] = ()
    compute: FeatureFn | None = field(default=None, hash=False, compare=False)

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"


FEATURE_REGISTRY: dict[str, FeatureSpec] = {}


def register(spec: FeatureSpec) -> FeatureSpec:
    if spec.name in FEATURE_REGISTRY:
        raise ValueError(f"Duplicate feature registration: {spec.name}")
    FEATURE_REGISTRY[spec.name] = spec
    return spec


def get_feature(name: str) -> FeatureSpec:
    try:
        return FEATURE_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown feature: {name}") from exc


def list_features() -> list[FeatureSpec]:
    return sorted(FEATURE_REGISTRY.values(), key=lambda s: s.name)
