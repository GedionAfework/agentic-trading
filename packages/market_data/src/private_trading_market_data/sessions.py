from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time


@dataclass(slots=True, frozen=True)
class SessionWindow:
    code: str
    start_utc: time
    end_utc: time


# Forex scaffolding only — crypto is always open.
FOREX_SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("asia", time(0, 0), time(9, 0)),
    SessionWindow("london", time(7, 0), time(16, 0)),
    SessionWindow("new_york", time(12, 0), time(21, 0)),
)


def is_market_open(asset_class: str, at: datetime | None = None) -> bool:
    if asset_class.lower() == "crypto":
        return True
    # FX weekend closed (Sat 00:00 UTC through Sun 21:00 UTC simplified)
    current = at or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    weekday = current.weekday()  # Mon=0 .. Sun=6
    if weekday == 5:
        return False
    if weekday == 6 and current.time() < time(21, 0):
        return False
    return True


def active_forex_sessions(at: datetime | None = None) -> list[str]:
    current = at or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    if not is_market_open("fx", current):
        return []
    t = current.timetz().replace(tzinfo=None)
    active: list[str] = []
    for window in FOREX_SESSIONS:
        if window.start_utc <= window.end_utc:
            if window.start_utc <= t < window.end_utc:
                active.append(window.code)
        else:
            # wraps midnight
            if t >= window.start_utc or t < window.end_utc:
                active.append(window.code)
    return active
