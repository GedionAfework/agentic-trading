from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from private_trading_agents.explain import explanation_invents_numbers

from private_trading_analytics.metrics import INSUFFICIENT_N, SMALL_N

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _fmt(value: float | None, places: int = 4) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(round(float(value), places))), "f")


def narrate_performance(snapshot: dict[str, Any]) -> str:
    """Journal-agent narration: restates SQL aggregate fields only."""
    metrics = snapshot.get("metrics") or {}
    cohort = snapshot["cohort"]
    n = int(snapshot["sample_size"])
    status = snapshot["sample_status"]
    extra: list[str] = [
        str(n),
        str(snapshot.get("strategy_code") or "*"),
        str(INSUFFICIENT_N),
        str(SMALL_N),
    ]
    for key in ("win_count", "loss_count", "with_realized_r", "trade_count"):
        if metrics.get(key) is not None:
            extra.append(str(int(metrics[key])))
    for key in ("win_rate", "mean_r", "sum_r", "mean_pnl", "sum_pnl"):
        text = _fmt(metrics.get(key))
        if text:
            extra.append(text)
            extra.append(text.rstrip("0").rstrip(".") if "." in text else text)
    for warn in snapshot.get("warnings") or []:
        # Allow digits that already appear in SQL-derived warning strings.
        extra.extend(_NUMBER.findall(str(warn)))

    parts = [
        f"Cohort {cohort} performance snapshot.",
        f"Sample size {n} with status {status}.",
        (
            f"Slice strategy={snapshot.get('strategy_code')} "
            f"symbol={snapshot.get('instrument_symbol')} "
            f"timeframe={snapshot.get('timeframe')} "
            f"session={snapshot.get('session_bucket')}."
        ),
    ]
    wr = _fmt(metrics.get("win_rate"))
    mean_r = _fmt(metrics.get("mean_r"))
    sum_r = _fmt(metrics.get("sum_r"))
    if wr is not None:
        parts.append(f"Win rate {wr} from {int(metrics.get('win_count') or 0)} wins.")
    else:
        parts.append("Win rate unavailable.")
    if mean_r is not None:
        parts.append(f"Mean realized R {mean_r}.")
    else:
        parts.append("Mean realized R unavailable.")
    if sum_r is not None:
        parts.append(f"Sum realized R {sum_r}.")
    warns = snapshot.get("warnings") or []
    if warns:
        parts.append("Warnings: " + "; ".join(str(w) for w in warns) + ".")
    else:
        parts.append("Warnings: none.")
    parts.append(
        "Numbers are copied from SQL aggregates for this cohort only; "
        "backtest and paper cohorts are never merged."
    )
    text = " ".join(parts)
    facts = {
        "strategy_version_no": 0,
        "extra_numbers": extra,
    }
    invented = explanation_invents_numbers(text, facts)
    if invented:
        raise ValueError(f"performance narration invented numbers: {invented}")
    return text


def narrate_calibration(snapshot: dict[str, Any]) -> str:
    cohort = snapshot["cohort"]
    n = int(snapshot["sample_size"])
    band_field = snapshot["band_field"]
    extra = [str(n), band_field]
    parts = [
        f"Cohort {cohort} calibration on {band_field}.",
        f"Sample size {n} with status {snapshot['sample_status']}.",
    ]
    for band, payload in sorted((snapshot.get("bands") or {}).items()):
        bn = int(payload.get("sample_size") or 0)
        extra.append(str(bn))
        wr = _fmt(payload.get("win_rate"))
        mr = _fmt(payload.get("mean_r"))
        if wr:
            extra.append(wr)
        if mr:
            extra.append(mr)
        bit = f"Band {band}: n={bn}"
        if wr is not None:
            bit += f" win_rate={wr}"
        if mr is not None:
            bit += f" mean_r={mr}"
        bit += "."
        parts.append(bit)
    flags = snapshot.get("drift_flags") or []
    if flags:
        parts.append("Drift flags: " + "; ".join(str(f) for f in flags) + ".")
    else:
        parts.append("Drift flags: none.")
    parts.append("Retrain is never triggered by these flags alone.")
    text = " ".join(parts)
    invented = explanation_invents_numbers(text, {"strategy_version_no": 0, "extra_numbers": extra})
    if invented:
        raise ValueError(f"calibration narration invented numbers: {invented}")
    return text
