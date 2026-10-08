from __future__ import annotations

import uuid
from typing import Any

from private_trading_db.models.paper import JournalEntry, PaperTrade
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_paper_journal_entry(
    session: AsyncSession,
    *,
    trade: PaperTrade,
    summary: str,
    details: dict[str, Any] | None = None,
) -> JournalEntry:
    existing = await session.execute(
        select(JournalEntry).where(JournalEntry.paper_trade_id == trade.id)
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row
    entry = JournalEntry(
        owner_user_id=trade.owner_user_id,
        paper_trade_id=trade.id,
        cohort="paper",
        instrument_symbol=trade.instrument_symbol,
        timeframe=trade.timeframe,
        direction=trade.direction,
        outcome=trade.exit_reason or "closed",
        realized_r=trade.realized_r,
        realized_pnl=trade.realized_pnl,
        summary=summary,
        details={
            "label": "PAPER",
            "entry_price": None if trade.entry_price is None else str(trade.entry_price),
            "exit_price": None if trade.exit_price is None else str(trade.exit_price),
            "stop_price": str(trade.stop_price),
            "target_price": str(trade.target_price),
            "bars_held": trade.bars_held,
            "costs": str(trade.costs),
            **(details or {}),
        },
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_journal_entries(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    cohort: str | None = "paper",
    limit: int = 50,
) -> list[JournalEntry]:
    stmt = select(JournalEntry).where(JournalEntry.owner_user_id == owner_user_id)
    if cohort:
        stmt = stmt.where(JournalEntry.cohort == cohort)
    stmt = stmt.order_by(JournalEntry.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
