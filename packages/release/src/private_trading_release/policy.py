from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

REQUIRED_GATES = ("A", "B", "C", "D", "E", "F", "G")
CONSERVATIVE_ACTIONS = frozenset({"ENTER", "WAIT", "HOLD", "EXIT", "NO_SETUP"})
# Production alerts: only ENTER setups that cleared risk (payload carries risk_approved).
ALERTABLE_ACTIONS = frozenset({"ENTER"})


@dataclass
class ReleasePolicy:
    """Narrow production alert scope. Lab mode when live_alerts_enabled is false."""

    live_alerts_enabled: bool = False
    approved_symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    approved_timeframes: list[str] = field(default_factory=lambda: ["15m", "1h"])
    channels: list[str] = field(default_factory=lambda: ["telegram"])
    # Quiet hours in UTC [start, end). Empty/null disables.
    quiet_hours_utc_start: int | None = 22
    quiet_hours_utc_end: int | None = 6
    require_checklist: bool = True
    require_soak: bool = True
    require_integrity: bool = True
    # Conservative: only ENTER with risk_approved true and confidence not "low"
    min_confidence_band: str = "medium"
    allow_actions: list[str] = field(default_factory=lambda: ["ENTER"])
    notes: str = "Phase 20 alerts-only release. Broker execution remains undeployed."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ReleasePolicy:
        if not raw:
            return cls()
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in raw.items() if k in known}
        return cls(**data)


DEFAULT_POLICY = ReleasePolicy()

_BAND_RANK = {"low": 0, "medium": 1, "high": 2, "unknown": -1}


def in_quiet_hours(
    now: datetime,
    *,
    start: int | None,
    end: int | None,
) -> bool:
    if start is None or end is None:
        return False
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return False
    hour = now.replace(tzinfo=UTC).hour if now.tzinfo is None else now.astimezone(UTC).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # Wraps midnight (e.g. 22 → 6)
    return hour >= start or hour < end


def band_meets_minimum(band: str | None, minimum: str) -> bool:
    return _BAND_RANK.get((band or "unknown").lower(), -1) >= _BAND_RANK.get(minimum.lower(), 1)


def evaluate_alert_gate(
    *,
    policy: ReleasePolicy,
    symbol: str,
    timeframe: str,
    action: str,
    confidence_band: str | None,
    risk_approved: bool | None,
    now: datetime,
    notifications_enabled: bool,
    checklist_complete: bool,
    soak_complete: bool,
    integrity_ok: bool,
    active_waiver_codes: set[str],
    channel: str = "telegram",
) -> dict[str, Any]:
    """Decide whether a candidate may enter the live alert outbox.

    Lab/dev: live_alerts_enabled=false → allow (kill switch still applies).
    Production: live_alerts_enabled=true → narrow gates.
    """
    reasons: list[str] = []
    if not notifications_enabled:
        return {
            "allow": False,
            "publish_state": "suppressed_kill_switch",
            "mode": "kill_switch",
            "reasons": ["notifications_enabled=false"],
        }

    if not policy.live_alerts_enabled:
        return {
            "allow": True,
            "publish_state": "published",
            "mode": "lab",
            "reasons": ["live_alerts_enabled=false; lab/dev alert path"],
        }

    # --- production mode ---
    if channel not in policy.channels:
        reasons.append(f"channel_{channel}_not_in_scope")
    if symbol not in policy.approved_symbols:
        reasons.append(f"symbol_not_approved:{symbol}")
    if timeframe not in policy.approved_timeframes:
        reasons.append(f"timeframe_not_approved:{timeframe}")
    if action not in policy.allow_actions:
        reasons.append(f"action_not_in_scope:{action}")
    if not risk_approved:
        reasons.append("risk_not_approved")
    if not band_meets_minimum(confidence_band, policy.min_confidence_band):
        reasons.append(f"confidence_below_min:{confidence_band}")
    if in_quiet_hours(
        now,
        start=policy.quiet_hours_utc_start,
        end=policy.quiet_hours_utc_end,
    ):
        reasons.append("quiet_hours_utc")

    if (
        policy.require_checklist
        and not checklist_complete
        and "gate_checklist_incomplete" not in active_waiver_codes
    ):
        reasons.append("checklist_incomplete")
    if (
        policy.require_soak
        and not soak_complete
        and "gate_f_soak_incomplete" not in active_waiver_codes
    ):
        reasons.append("soak_incomplete")
    if (
        policy.require_integrity
        and not integrity_ok
        and "gate_f_integrity_defects" not in active_waiver_codes
    ):
        reasons.append("integrity_defects")

    if reasons:
        return {
            "allow": False,
            "publish_state": "suppressed_release_gate",
            "mode": "production",
            "reasons": reasons,
        }
    return {
        "allow": True,
        "publish_state": "published",
        "mode": "production",
        "reasons": ["release_gates_passed"],
    }
