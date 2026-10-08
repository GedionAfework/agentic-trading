from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from private_trading_db.services.audit import record_audit
from private_trading_journal.service import list_journal_entries
from private_trading_paper_trade.service import (
    accept_decision,
    account_summary,
    cancel_trade,
    ensure_paper_account,
    get_trade,
    list_events,
    list_trades,
    monitor_account,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.paper import (
    AcceptPaperTradeRequest,
    JournalEntryOut,
    MonitorOut,
    PaperAccountOut,
    PaperEventOut,
    PaperTradeDetailOut,
    PaperTradeOut,
)

router = APIRouter(prefix="/paper", tags=["paper"])


def _trade_out(trade) -> PaperTradeOut:
    return PaperTradeOut(
        id=trade.id,
        account_id=trade.account_id,
        decision_record_id=trade.decision_record_id,
        candidate_id=trade.candidate_id,
        instrument_symbol=trade.instrument_symbol,
        timeframe=trade.timeframe,
        direction=trade.direction,
        status=trade.status,
        label=trade.label,
        signal_bar_open_time=trade.signal_bar_open_time,
        planned_entry=float(trade.planned_entry),
        stop_price=float(trade.stop_price),
        target_price=float(trade.target_price),
        invalidation_price=(
            None if trade.invalidation_price is None else float(trade.invalidation_price)
        ),
        qty=float(trade.qty),
        risk_amount=float(trade.risk_amount),
        fill_model=dict(trade.fill_model or {}),
        entry_price=None if trade.entry_price is None else float(trade.entry_price),
        entry_bar_open_time=trade.entry_bar_open_time,
        exit_price=None if trade.exit_price is None else float(trade.exit_price),
        exit_bar_open_time=trade.exit_bar_open_time,
        exit_reason=trade.exit_reason,
        realized_pnl=None if trade.realized_pnl is None else float(trade.realized_pnl),
        realized_r=None if trade.realized_r is None else float(trade.realized_r),
        costs=float(trade.costs or 0),
        bars_held=int(trade.bars_held or 0),
        journal_entry_id=trade.journal_entry_id,
        notes=list(trade.notes or []),
        created_at=trade.created_at,
        closed_at=trade.closed_at,
    )


@router.get("/account", response_model=PaperAccountOut)
async def get_account(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaperAccountOut:
    user.require_roles("owner", "admin", "viewer")
    summary = await account_summary(session, owner_user_id=user.id)
    return PaperAccountOut(
        account_id=uuid.UUID(summary["account_id"]),
        label=summary["label"],
        currency=summary["currency"],
        starting_equity=summary["starting_equity"],
        equity=summary["equity"],
        fill_model=summary["fill_model"],
        trades_by_status=summary["trades_by_status"],
        closed_trades=summary["closed_trades"],
        sum_realized_r=summary["sum_realized_r"],
        soak=summary["soak"],
        integrity=summary["integrity"],
    )


@router.post("/account", response_model=PaperAccountOut)
async def post_account(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaperAccountOut:
    user.require_roles("owner", "admin")
    await ensure_paper_account(session, owner_user_id=user.id)
    await record_audit(
        session,
        action="paper.account_ensured",
        actor_type="user",
        actor_id=user.id,
        resource_type="paper_account",
        correlation_id=get_correlation_id(request),
        metadata={"label": "PAPER"},
    )
    await session.commit()
    summary = await account_summary(session, owner_user_id=user.id)
    return PaperAccountOut(
        account_id=uuid.UUID(summary["account_id"]),
        label=summary["label"],
        currency=summary["currency"],
        starting_equity=summary["starting_equity"],
        equity=summary["equity"],
        fill_model=summary["fill_model"],
        trades_by_status=summary["trades_by_status"],
        closed_trades=summary["closed_trades"],
        sum_realized_r=summary["sum_realized_r"],
        soak=summary["soak"],
        integrity=summary["integrity"],
    )


@router.post("/trades", response_model=PaperTradeOut)
async def post_trade(
    body: AcceptPaperTradeRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaperTradeOut:
    user.require_roles("owner", "admin")
    trade = await accept_decision(
        session,
        owner_user_id=user.id,
        decision_record_id=body.decision_record_id,
        candidate_id=body.candidate_id,
    )
    await record_audit(
        session,
        action="paper.trade_accepted",
        actor_type="user",
        actor_id=user.id,
        resource_type="paper_trade",
        resource_id=trade.id,
        correlation_id=get_correlation_id(request),
        metadata={"status": trade.status, "label": trade.label},
    )
    await session.commit()
    return _trade_out(trade)


@router.get("/trades", response_model=list[PaperTradeOut])
async def get_trades(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PaperTradeOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_trades(session, owner_user_id=user.id, status=status, limit=limit)
    return [_trade_out(t) for t in rows]


@router.get("/trades/{trade_id}", response_model=PaperTradeDetailOut)
async def get_trade_detail(
    trade_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaperTradeDetailOut:
    user.require_roles("owner", "admin", "viewer")
    trade = await get_trade(session, owner_user_id=user.id, trade_id=trade_id)
    if trade is None:
        from private_trading_core.errors import NotFoundError

        raise NotFoundError("Paper trade not found")
    events = await list_events(session, trade_id=trade.id)
    base = _trade_out(trade).model_dump()
    return PaperTradeDetailOut(
        **base,
        events=[
            PaperEventOut(
                id=e.id,
                event_type=e.event_type,
                bar_open_time=e.bar_open_time,
                payload=dict(e.payload or {}),
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@router.post("/trades/{trade_id}/cancel", response_model=PaperTradeOut)
async def post_cancel(
    trade_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaperTradeOut:
    user.require_roles("owner", "admin")
    trade = await cancel_trade(session, owner_user_id=user.id, trade_id=trade_id)
    await record_audit(
        session,
        action="paper.trade_cancelled",
        actor_type="user",
        actor_id=user.id,
        resource_type="paper_trade",
        resource_id=trade.id,
        correlation_id=get_correlation_id(request),
        metadata={"label": "PAPER"},
    )
    await session.commit()
    return _trade_out(trade)


@router.post("/monitor", response_model=MonitorOut)
async def post_monitor(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MonitorOut:
    user.require_roles("owner", "admin")
    result = await monitor_account(session, owner_user_id=user.id)
    await record_audit(
        session,
        action="paper.monitor_run",
        actor_type="user",
        actor_id=user.id,
        resource_type="paper",
        correlation_id=get_correlation_id(request),
        metadata=dict(result),
    )
    await session.commit()
    return MonitorOut(**result)


@router.get("/journal", response_model=list[JournalEntryOut])
async def get_journal(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JournalEntryOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_journal_entries(session, owner_user_id=user.id, cohort="paper", limit=limit)
    return [
        JournalEntryOut(
            id=r.id,
            cohort=r.cohort,
            instrument_symbol=r.instrument_symbol,
            timeframe=r.timeframe,
            direction=r.direction,
            outcome=r.outcome,
            realized_r=None if r.realized_r is None else float(r.realized_r),
            realized_pnl=None if r.realized_pnl is None else float(r.realized_pnl),
            summary=r.summary,
            details=dict(r.details or {}),
            paper_trade_id=r.paper_trade_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
