from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from private_trading_risk.types import WeekendPolicy

RISK_ENGINE_VERSION = "0.1.0"

# Engineering candidates until D-01 / D-06 / D-07 lock — never silent.
DEFAULT_POLICY_CONFIG: dict[str, Any] = {
    "min_rr": 2.0,
    "max_risk_pct": 0.5,
    "max_open_risk_pct": 2.0,
    "require_invalidation": True,
    "require_fresh_data": True,
    "weekend_policy": WeekendPolicy.WARN.value,  # D-07 OPEN
    "event_blackout_enabled": False,  # D-06 OPEN
    "event_blackout_minutes_before": 0,
    "event_blackout_minutes_after": 0,
    "allow_paper_sizing": True,
    "asset_class": "crypto",
    "lock_status": "engineering_candidate",
    "decision_refs": ["D-01", "D-06", "D-07"],
}


def default_policy_config(**overrides: Any) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_POLICY_CONFIG)
    cfg.update(overrides)
    return cfg


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))
