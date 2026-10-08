"""FR-SIG-008 / BR-005: automated broker execution must stay undeployed."""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path
from typing import Any

_BROKER_ENV_PREFIXES = ("BROKER_", "EXCHANGE_API_", "BINANCE_API_KEY", "BINANCE_API_SECRET")


def execution_package_present() -> bool:
    if find_spec("private_trading_execution") is not None:
        return True
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "pyproject.toml").exists():
            return (parent / "packages" / "execution").exists()
    return False


def broker_env_present() -> list[str]:
    found: list[str] = []
    for key, value in os.environ.items():
        if not value or not str(value).strip():
            continue
        upper = key.upper()
        if upper.startswith("BROKER_") or upper.startswith("EXCHANGE_API_"):
            found.append(key)
        if upper in {"BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_SECRET_KEY"}:
            # Public market data uses BINANCE_BASE_URL only — keys would imply trading.
            found.append(key)
    return sorted(found)


def execution_status() -> dict[str, Any]:
    pkg = execution_package_present()
    envs = broker_env_present()
    ok = (not pkg) and (not envs)
    return {
        "broker_execution": "disabled",
        "execution_package_present": pkg,
        "broker_credential_env_vars": envs,
        "ok": ok,
        "policy": "FR-SIG-008 / BR-005 — alerts only; no automated broker execution.",
    }


def assert_execution_undeployed() -> None:
    status = execution_status()
    if not status["ok"]:
        raise RuntimeError(
            "Broker execution controls violated: "
            f"package={status['execution_package_present']} "
            f"envs={status['broker_credential_env_vars']}"
        )
