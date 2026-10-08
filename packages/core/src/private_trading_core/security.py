"""Shared security helpers for Gate A (auth/secrets/upload abuse)."""

from __future__ import annotations

import re
from collections.abc import Iterable

# High-signal patterns for local/CI secret scanning. Not a substitute for gitleaks.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key_assignment", re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|private[_-]?key)\s*[:=]\s*['\"][^'\"]{16,}['\"]"
    )),
    (
        "jwt_hmac_example",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    ("telegram_bot_token", re.compile(r"\d{8,12}:[A-Za-z0-9_-]{30,}")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)

_SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".lock",
    ".pyc",
    ".woff",
    ".woff2",
)


def scan_text_for_secrets(text: str, *, path: str = "<memory>") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            # Allow documented placeholders in docs/examples
            snippet = match.group(0)
            if "EXAMPLE" in snippet.upper() or "CHANGEME" in snippet.upper():
                continue
            if "dev-only-change-me" in snippet:
                continue
            findings.append(
                {
                    "rule": name,
                    "path": path,
                    "snippet": snippet[:24] + "…",
                }
            )
    return findings


def should_skip_path(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    if any(part in lowered for part in ("/.git/", "/.venv/", "/node_modules/", "/__pycache__/")):
        return True
    return lowered.endswith(_SKIP_SUFFIXES)


def scan_paths(paths: Iterable[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in paths:
        if should_skip_path(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
        except OSError:
            continue
        findings.extend(scan_text_for_secrets(text, path=path))
    return findings
