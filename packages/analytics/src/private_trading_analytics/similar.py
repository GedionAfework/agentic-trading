from __future__ import annotations

import uuid
from typing import Any

from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.paper import PaperTrade
from private_trading_db.models.scanner import SignalCandidate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _similarity_score(probe: SignalCandidate, other: SignalCandidate) -> int:
    score = 0
    if other.strategy_code == probe.strategy_code:
        score += 4
    if other.instrument_symbol == probe.instrument_symbol:
        score += 3
    if other.timeframe == probe.timeframe:
        score += 2
    if other.action == probe.action:
        score += 2
    if other.signal_type == probe.signal_type:
        score += 2
    if other.setup_anchor == probe.setup_anchor:
        score += 3
    return score


async def find_similar_setups(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    candidate_id: uuid.UUID,
    limit: int = 10,
) -> dict[str, Any]:
    probe_result = await session.execute(
        select(SignalCandidate).where(
            SignalCandidate.id == candidate_id,
            SignalCandidate.owner_user_id == owner_user_id,
        )
    )
    probe = probe_result.scalar_one_or_none()
    if probe is None:
        return {"probe": None, "matches": []}

    result = await session.execute(
        select(SignalCandidate)
        .where(
            SignalCandidate.owner_user_id == owner_user_id,
            SignalCandidate.id != probe.id,
            SignalCandidate.strategy_code == probe.strategy_code,
        )
        .order_by(SignalCandidate.last_seen_at.desc())
        .limit(200)
    )
    candidates = list(result.scalars().all())
    scored = sorted(
        (( _similarity_score(probe, c), c) for c in candidates),
        key=lambda item: (-item[0], item[1].last_seen_at),
    )
    matches: list[dict[str, Any]] = []
    for score, cand in scored[:limit]:
        if score < 6:
            continue
        paper = await session.execute(
            select(PaperTrade).where(
                PaperTrade.candidate_id == cand.id,
                PaperTrade.status == "closed",
            )
        )
        trade = paper.scalar_one_or_none()
        decision = None
        if cand.decision_record_id:
            dr = await session.execute(
                select(DecisionRecord).where(DecisionRecord.id == cand.decision_record_id)
            )
            decision = dr.scalar_one_or_none()
        matches.append(
            {
                "candidate_id": str(cand.id),
                "score": score,
                "instrument_symbol": cand.instrument_symbol,
                "timeframe": cand.timeframe,
                "action": cand.action,
                "signal_type": cand.signal_type,
                "setup_anchor": cand.setup_anchor,
                "strategy_code": cand.strategy_code,
                "candle_open_time": cand.candle_open_time.isoformat(),
                "paper_outcome": None
                if trade is None
                else {
                    "cohort": "paper",
                    "exit_reason": trade.exit_reason,
                    "realized_r": None if trade.realized_r is None else float(trade.realized_r),
                    "status": trade.status,
                },
                "confidence_band": None if decision is None else decision.confidence_band,
            }
        )
    return {
        "probe": {
            "candidate_id": str(probe.id),
            "instrument_symbol": probe.instrument_symbol,
            "timeframe": probe.timeframe,
            "action": probe.action,
            "signal_type": probe.signal_type,
            "setup_anchor": probe.setup_anchor,
            "strategy_code": probe.strategy_code,
        },
        "matches": matches,
        "note": "Similarity is deterministic feature overlap; outcomes stay cohort-labeled.",
    }
