from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.ops import OutboxEvent
from private_trading_features.types import CandleBar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_agents.workflow import CitationRef, DecisionSnapshot, run_decision_workflow


def _num(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


async def persist_decision(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    snapshot: DecisionSnapshot,
) -> DecisionRecord:
    record = DecisionRecord(
        owner_user_id=owner_user_id,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        bar_open_time=snapshot.bar_open_time,
        action=snapshot.action.value,
        direction=snapshot.direction,
        setup_state=snapshot.setup_state,
        confidence_band=snapshot.confidence_band,
        strategy_code=snapshot.strategy_code,
        strategy_version_no=snapshot.strategy_version_no,
        risk_approved=snapshot.risk_approved,
        entry_price=_num(snapshot.entry_price),
        stop_price=_num(snapshot.stop_price),
        target_price=_num(snapshot.target_price),
        rr_ratio=_num(snapshot.rr_ratio),
        model_id=snapshot.model_id,
        model_score=snapshot.model_score,
        model_band=snapshot.model_band,
        explanation=snapshot.explanation,
        explanation_source=snapshot.explanation_source,
        evidence=snapshot.evidence,
        workflow=snapshot.workflow,
        hard_blockers=snapshot.hard_blockers,
    )
    session.add(record)
    await session.flush()
    session.add(
        OutboxEvent(
            topic="decision.snapshot",
            aggregate_type="decision_record",
            aggregate_id=record.id,
            payload={
                "action": record.action,
                "symbol": record.symbol,
                "timeframe": record.timeframe,
                "setup_state": record.setup_state,
                "confidence_band": record.confidence_band,
                "risk_approved": record.risk_approved,
            },
        )
    )
    await session.commit()
    return record


async def get_decision_record(session: AsyncSession, record_id: uuid.UUID) -> DecisionRecord | None:
    result = await session.execute(select(DecisionRecord).where(DecisionRecord.id == record_id))
    return result.scalar_one_or_none()


async def run_and_persist(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    bars: list[CandleBar],
    symbol: str,
    timeframe: str,
    bar_index: int | None = None,
    data_fresh: bool = True,
    market_actionable: bool = True,
    position_state: str = "flat",
    citations: list[dict[str, Any]] | None = None,
    model: Any = None,
    model_id: uuid.UUID | None = None,
    model_mode: str | None = None,
) -> DecisionRecord:
    snapshot = run_decision_workflow(
        bars,
        symbol=symbol,
        timeframe=timeframe,
        bar_index=bar_index,
        data_fresh=data_fresh,
        market_actionable=market_actionable,
        position_state=position_state,  # type: ignore[arg-type]
        citations=[
            CitationRef(
                citation_id=item["citation_id"],
                excerpt=item.get("excerpt") or "",
                document_id=item.get("document_id"),
            )
            for item in (citations or [])
        ],
        model=model,
        model_id=model_id,
        model_mode=model_mode,
    )
    return await persist_decision(session, owner_user_id=owner_user_id, snapshot=snapshot)
