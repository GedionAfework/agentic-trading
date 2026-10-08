"""Lightweight Prometheus text exposition without an external dependency."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._hist_sum: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._hist_count: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self.started_at = time.time()

    def inc(self, name: str, *, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._hist_sum[key] += value
            self._hist_count[key] += 1.0

    def render(self) -> str:
        lines: list[str] = [
            "# HELP pta_process_uptime_seconds Process uptime",
            "# TYPE pta_process_uptime_seconds gauge",
            f"pta_process_uptime_seconds {time.time() - self.started_at:.3f}",
        ]
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            hist_sum = list(self._hist_sum.items())
            hist_count = dict(self._hist_count)
        names_seen: set[str] = set()
        for (name, labels), value in sorted(counters):
            if name not in names_seen:
                lines.append(f"# TYPE {name} counter")
                names_seen.add(name)
            lines.append(f"{name}{_fmt_labels(labels)} {value}")
        for (name, labels), value in sorted(gauges):
            if name not in names_seen:
                lines.append(f"# TYPE {name} gauge")
                names_seen.add(name)
            lines.append(f"{name}{_fmt_labels(labels)} {value}")
        for (name, labels), total in sorted(hist_sum):
            base = f"{name}_sum"
            count_name = f"{name}_count"
            if name not in names_seen:
                lines.append(f"# TYPE {name} summary")
                names_seen.add(name)
            lines.append(f"{base}{_fmt_labels(labels)} {total}")
            lines.append(f"{count_name}{_fmt_labels(labels)} {hist_count[(name, labels)]}")
        lines.append("")
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {
                    f"{n}|{dict(lbl)}": v for (n, lbl), v in self._counters.items()
                },
                "gauges": {f"{n}|{dict(lbl)}": v for (n, lbl), v in self._gauges.items()},
            }


def _fmt_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels)
    return "{" + inner + "}"


REGISTRY = MetricsRegistry()
