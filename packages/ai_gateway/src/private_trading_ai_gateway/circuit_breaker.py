from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    _state: str = field(default="closed")

    @property
    def state(self) -> str:
        if (
            self._state == "open"
            and self.opened_at is not None
            and time.monotonic() - self.opened_at >= self.recovery_seconds
        ):
            self._state = "half_open"
        return self._state

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self._state = "closed"

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self._state = "open"
            self.opened_at = time.monotonic()
