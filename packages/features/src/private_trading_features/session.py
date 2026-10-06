from __future__ import annotations

from datetime import UTC

from private_trading_features.registry import FeatureSpec, register
from private_trading_features.types import CandleBar, FeatureValue, TriState

SESSION_VERSION = "1.0.0-ec"


def compute_crypto_session_open(bars: list[CandleBar], index: int) -> FeatureValue:
    """SES-001 EC scaffolding: crypto always open for feature layer."""
    name = "crypto_session_open"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, SESSION_VERSION, "index_out_of_range")
    return FeatureValue.of(
        name,
        SESSION_VERSION,
        status=TriState.TRUE,
        value=True,
        asset_class="crypto",
        definition_id="SES-001",
        lock_status="engineering_candidate",
        note="weekend_policy_owner_decision",
    )


def compute_bar_weekday(bars: list[CandleBar], index: int) -> FeatureValue:
    name = "bar_weekday"
    if index < 0 or index >= len(bars):
        return FeatureValue.unknown(name, SESSION_VERSION, "index_out_of_range")
    ts = bars[index].open_time
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    else:
        ts = ts.astimezone(UTC)
    return FeatureValue.of(
        name,
        SESSION_VERSION,
        status=TriState.TRUE,
        value=ts.weekday(),
        iso=ts.isoweekday(),
    )


register(
    FeatureSpec(
        name="crypto_session_open",
        version=SESSION_VERSION,
        lookback=1,
        description="Crypto market open flag (always true in v1 EC)",
        lock_status="engineering_candidate",
        definition_id="SES-001",
        compute=compute_crypto_session_open,
    )
)
register(
    FeatureSpec(
        name="bar_weekday",
        version=SESSION_VERSION,
        lookback=1,
        description="UTC weekday of bar open (Mon=0)",
        lock_status="engineering_candidate",
        compute=compute_bar_weekday,
    )
)
