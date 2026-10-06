from __future__ import annotations

import hashlib
import json
from datetime import datetime

from private_trading_features import atr as _atr  # noqa: F401
from private_trading_features import session as _session  # noqa: F401
from private_trading_features import structure as _structure  # noqa: F401
from private_trading_features import swings as _swings  # noqa: F401
from private_trading_features import volume as _volume  # noqa: F401
from private_trading_features.registry import FEATURE_REGISTRY, get_feature, list_features
from private_trading_features.types import CandleBar, FeatureSnapshot, FeatureValue, TriState

FEATURE_ENGINE_VERSION = "0.1.0"


def assert_no_lookahead(bars: list[CandleBar], index: int) -> None:
    if index < 0 or index >= len(bars):
        raise IndexError(f"Feature index {index} out of range for {len(bars)} bars")


def cache_key(
    *,
    feature_names: list[str],
    bar_index: int,
    as_of: datetime,
    engine_version: str = FEATURE_ENGINE_VERSION,
) -> str:
    specs = []
    for name in sorted(feature_names):
        spec = get_feature(name)
        specs.append({"name": spec.name, "version": spec.version, "lookback": spec.lookback})
    payload = {
        "engine": engine_version,
        "as_of": as_of.isoformat(),
        "bar_index": bar_index,
        "features": specs,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_feature(name: str, bars: list[CandleBar], index: int) -> FeatureValue:
    assert_no_lookahead(bars, index)
    spec = get_feature(name)
    if spec.compute is None:
        return FeatureValue.unknown(name, spec.version, "no_compute_fn")
    # Pass only bars up to index inclusive — hard no look-ahead boundary.
    window = bars[: index + 1]
    return spec.compute(window, index)


def compute_many(
    bars: list[CandleBar],
    index: int,
    names: list[str] | None = None,
) -> dict[str, FeatureValue]:
    assert_no_lookahead(bars, index)
    selected = names or [s.name for s in list_features()]
    return {name: compute_feature(name, bars, index) for name in selected}


def compute_snapshot(
    bars: list[CandleBar],
    index: int,
    names: list[str] | None = None,
) -> FeatureSnapshot:
    values = compute_many(bars, index, names)
    as_of = bars[index].open_time
    key = cache_key(
        feature_names=list(values.keys()),
        bar_index=index,
        as_of=as_of,
    )
    return FeatureSnapshot(
        as_of=as_of,
        bar_index=index,
        feature_engine_version=FEATURE_ENGINE_VERSION,
        values=values,
        cache_key=key,
    )


def any_unknown(values: dict[str, FeatureValue], *, required: list[str] | None = None) -> bool:
    keys = required or list(values.keys())
    return any(values[k].status == TriState.UNKNOWN for k in keys if k in values)


__all__ = [
    "FEATURE_ENGINE_VERSION",
    "FEATURE_REGISTRY",
    "any_unknown",
    "cache_key",
    "compute_feature",
    "compute_many",
    "compute_snapshot",
    "get_feature",
    "list_features",
]
