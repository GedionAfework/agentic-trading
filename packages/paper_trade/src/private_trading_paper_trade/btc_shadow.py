"""Forward-only success rate of paper trades split by the BTC regime shadow tag.

This is the honest evidence for (or against) a future BTC-regime hypothesis:
only paper trades opened after the tag existed, never 2022–2026 history.
Read-only. A split never changes routing, sizing, or gates.
"""

from __future__ import annotations

import uuid
from typing import Any

from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.paper import PaperTrade
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_paper_trade.engine import STATUS_CLOSED

# Below this per bucket, the split is noise; say so instead of implying an edge.
MIN_TRADES_PER_BUCKET = 30


def _bucket_stats(rs: list[float]) -> dict[str, Any]:
    n = len(rs)
    if not n:
        return {"trades": 0, "win_rate": None, "mean_r": None, "sum_r": 0.0}
    return {
        "trades": n,
        "win_rate": sum(r > 0 for r in rs) / n,
        "mean_r": sum(rs) / n,
        "sum_r": sum(rs),
    }


def split_by_btc_regime(rows: list[tuple[str, str, float]]) -> dict[str, Any]:
    """Pure. rows = (model_code, label in risk_on|risk_off|unknown, realized_r)."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for code, label, r in rows:
        bucket = label if label in ("risk_on", "risk_off") else "unknown"
        grouped.setdefault(code, {"risk_on": [], "risk_off": [], "unknown": []})[
            bucket
        ].append(r)
    models = []
    for code in sorted(grouped):
        buckets = {name: _bucket_stats(rs) for name, rs in grouped[code].items()}
        on, off = buckets["risk_on"]["trades"], buckets["risk_off"]["trades"]
        enough = on >= MIN_TRADES_PER_BUCKET and off >= MIN_TRADES_PER_BUCKET
        models.append(
            {
                "model_code": code,
                **buckets,
                "enough_sample": enough,
                "verdict": (
                    "compare" if enough else
                    f"insufficient: need {MIN_TRADES_PER_BUCKET} closed trades in each of "
                    f"risk-on/off (have {on}/{off})"
                ),
            }
        )
    return {
        "models": models,
        "min_trades_per_bucket": MIN_TRADES_PER_BUCKET,
        "shadow_only": True,
        "note": (
            "Forward paper trades only. A difference here is a reason to write a new "
            "hypothesis and walk-forward it, never to switch a filter on directly."
        ),
    }


async def btc_regime_shadow_report(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    from private_trading_paper_trade.service import soak_trade_model_code

    result = await session.execute(
        select(PaperTrade, DecisionRecord.evidence)
        .join(DecisionRecord, DecisionRecord.id == PaperTrade.decision_record_id, isouter=True)
        .where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status == STATUS_CLOSED,
            PaperTrade.realized_r.is_not(None),
        )
    )
    rows: list[tuple[str, str, float]] = []
    for trade, evidence in result.all():
        code = soak_trade_model_code(trade.fill_model) or "unattributed"
        tag = dict((evidence or {}).get("btc_regime_shadow") or {})
        rows.append((code, str(tag.get("label") or "unknown"), float(trade.realized_r)))
    return split_by_btc_regime(rows)
