#!/usr/bin/env python3
"""Repo secret scan for CI / local Gate A checks."""

from __future__ import annotations

import sys
from pathlib import Path

from private_trading_core.security import scan_paths, should_skip_path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = {
    # Documented insecure defaults — blocked in production via production_settings_errors
    str(ROOT / "packages" / "core" / "src" / "private_trading_core" / "config.py"),
}


def main() -> int:
    paths: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path)
        if should_skip_path(rel):
            continue
        if "/tests/" in path.as_posix().replace("\\", "/") or "\\tests\\" in rel:
            continue
        if path.suffix.lower() in {
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".toml",
            ".py",
            ".ts",
            ".tsx",
            ".env.example",
        } or path.name in {".env.example", "Dockerfile"}:
            paths.append(rel)
    findings = [f for f in scan_paths(paths) if f["path"] not in ALLOWLIST]
    # Filter config.py placeholder jwt default — still allowlisted above
    if findings:
        print("secret_scan FAILED")
        for item in findings:
            print(f"{item['rule']}: {item['path']} :: {item['snippet']}")
        return 1
    print(f"secret_scan OK files={len(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
