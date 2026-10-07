from __future__ import annotations

import re

# Templates must not claim guaranteed profit / certainty.
_FORBIDDEN = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bguaranteed?\b",
        r"\brisk[-\s]?free\b",
        r"\b100%\s*(win|sure|certain)\b",
        r"\bcannot\s+lose\b",
        r"\bsure\s+profit\b",
        r"\bno\s+risk\b",
    )
]


def vocabulary_violations(text: str | None) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    for pattern in _FORBIDDEN:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits
