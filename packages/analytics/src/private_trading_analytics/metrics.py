from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SAMPLE_INSUFFICIENT = "insufficient_sample"
SAMPLE_SMALL = "small_sample_warning"
SAMPLE_OK = "ok"

INSUFFICIENT_N = 10
SMALL_N = 30


def sample_status_for(n: int) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if n < INSUFFICIENT_N:
        warnings.append(
            f"sample_size={n} is below {INSUFFICIENT_N}; metrics are not decision-grade."
        )
        return SAMPLE_INSUFFICIENT, warnings
    if n < SMALL_N:
        warnings.append(
            f"sample_size={n} is below {SMALL_N}; treat summary stats as provisional."
        )
        return SAMPLE_SMALL, warnings
    return SAMPLE_OK, warnings


def session_bucket(ts: datetime | None) -> str:
    """UTC hour buckets: asia 0-7, europe 8-15, us 16-23. Unknown if missing."""
    if ts is None:
        return "unknown"
    hour = ts.astimezone().hour if ts.tzinfo else ts.hour
    if 0 <= hour < 8:
        return "asia"
    if 8 <= hour < 16:
        return "europe"
    return "us"


@dataclass(frozen=True)
class TradeRow:
    strategy_code: str
    instrument_symbol: str
    timeframe: str
    session_bucket: str
    direction: str
    exit_reason: str | None
    realized_r: float | None
    realized_pnl: float | None
    won: bool | None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def aggregate_trades(rows: list[TradeRow]) -> dict[str, Any]:
    """Pure aggregate from closed trade rows. Never invents missing R."""
    n = len(rows)
    status, warnings = sample_status_for(n)
    rs = [r.realized_r for r in rows if r.realized_r is not None]
    pnls = [r.realized_pnl for r in rows if r.realized_pnl is not None]
    wins = [r for r in rows if r.won is True]
    losses = [r for r in rows if r.won is False]
    by_exit: dict[str, int] = defaultdict(int)
    for r in rows:
        by_exit[r.exit_reason or "unknown"] += 1
    metrics: dict[str, Any] = {
        "trade_count": n,
        "with_realized_r": len(rs),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": (len(wins) / n) if n else None,
        "mean_r": _mean(rs),
        "sum_r": sum(rs) if rs else None,
        "mean_pnl": _mean(pnls),
        "sum_pnl": sum(pnls) if pnls else None,
        "exit_reasons": dict(by_exit),
    }
    return {
        "sample_size": n,
        "sample_status": status,
        "metrics": metrics,
        "warnings": warnings,
    }


def slice_key(
    *,
    strategy_code: str = "*",
    instrument_symbol: str = "*",
    timeframe: str = "*",
    session: str = "*",
) -> tuple[str, str, str, str]:
    return (strategy_code, instrument_symbol, timeframe, session)


def build_slices(rows: list[TradeRow]) -> list[dict[str, Any]]:
    """Overall + per strategy/symbol/TF/session slices. Each carries its own sample status."""
    groups: dict[tuple[str, str, str, str], list[TradeRow]] = defaultdict(list)
    for row in rows:
        groups[slice_key(strategy_code=row.strategy_code)].append(row)
        groups[slice_key(instrument_symbol=row.instrument_symbol)].append(row)
        groups[slice_key(timeframe=row.timeframe)].append(row)
        groups[slice_key(session=row.session_bucket)].append(row)
        groups[
            slice_key(
                strategy_code=row.strategy_code,
                instrument_symbol=row.instrument_symbol,
                timeframe=row.timeframe,
                session=row.session_bucket,
            )
        ].append(row)

    # Overall cohort aggregate
    out: list[dict[str, Any]] = []
    overall = aggregate_trades(rows)
    out.append(
        {
            "grain": "overall",
            "strategy_code": "*",
            "instrument_symbol": "*",
            "timeframe": "*",
            "session_bucket": "*",
            **overall,
        }
    )
    for key, group in sorted(groups.items()):
        if key == ("*", "*", "*", "*"):
            continue
        if not group:
            continue
        # Skip duplicate of overall-only keys that are empty combos
        sc, sym, tf, sess = key
        grain = "slice"
        if sum(1 for x in key if x != "*") == 1:
            grain = "dimension"
        agg = aggregate_trades(group)
        out.append(
            {
                "grain": grain,
                "strategy_code": sc,
                "instrument_symbol": sym,
                "timeframe": tf,
                "session_bucket": sess,
                **agg,
            }
        )
    return out
