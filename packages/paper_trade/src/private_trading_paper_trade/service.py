"""Paper account / trade persistence and monitoring against closed candles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from private_trading_core.errors import AppError, NotFoundError
from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.models.ops import OutboxEvent
from private_trading_db.models.paper import PaperAccount, PaperTrade, PaperTradeEvent
from private_trading_db.models.scanner import SignalCandidate
from private_trading_features.types import CandleBar
from private_trading_journal.service import create_paper_journal_entry
from private_trading_risk.sizing import paper_quantity
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_paper_trade.engine import (
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_READY,
    PaperPlan,
    evaluate_exit_on_bar,
    journal_summary,
    timeout_exit,
    try_fill_at_next_open,
    validate_plan,
)
from private_trading_paper_trade.fill_model import (
    PAPER_LABEL,
    default_fill_model,
    risk_pct,
)

DEFAULT_STARTING_EQUITY = Decimal("10000")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _f(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


async def _emit(
    session: AsyncSession,
    *,
    trade_id: uuid.UUID,
    event_type: str,
    bar_open_time: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        PaperTradeEvent(
            trade_id=trade_id,
            event_type=event_type,
            bar_open_time=bar_open_time,
            payload=payload or {},
        )
    )


async def ensure_paper_account(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    starting_equity: Decimal | None = None,
    fill_overrides: dict[str, Any] | None = None,
) -> PaperAccount:
    result = await session.execute(
        select(PaperAccount).where(
            PaperAccount.owner_user_id == owner_user_id, PaperAccount.label == PAPER_LABEL
        )
    )
    account = result.scalar_one_or_none()
    if account is not None:
        return account
    equity = starting_equity or DEFAULT_STARTING_EQUITY
    account = PaperAccount(
        owner_user_id=owner_user_id,
        label=PAPER_LABEL,
        starting_equity=_f(equity),
        equity=_f(equity),
        fill_model=default_fill_model(**(fill_overrides or {})),
        soak_started_at=datetime.now(UTC),
        soak_days_required=14,
        status="active",
    )
    session.add(account)
    await session.flush()
    return account


async def get_account(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> PaperAccount | None:
    result = await session.execute(
        select(PaperAccount).where(
            PaperAccount.owner_user_id == owner_user_id, PaperAccount.label == PAPER_LABEL
        )
    )
    return result.scalar_one_or_none()


async def load_bars_after(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: str,
    after: datetime,
    limit: int = 500,
) -> list[CandleBar]:
    instrument = await session.execute(
        select(Instrument).where(Instrument.canonical_symbol == symbol)
    )
    row = instrument.scalar_one_or_none()
    if row is None:
        return []
    result = await session.execute(
        select(Candle)
        .where(
            Candle.instrument_id == row.id,
            Candle.timeframe == timeframe,
            Candle.is_final.is_(True),
            Candle.open_time > after,
        )
        .order_by(Candle.open_time.asc())
        .limit(limit)
    )
    return [
        CandleBar(
            open_time=c.open_time,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            is_final=True,
        )
        for c in result.scalars().all()
    ]


def _invalidation_from_record(record: DecisionRecord) -> Decimal | None:
    evidence = dict(record.evidence or {})
    for key in ("invalidation_price", "invalidation", "structure_invalidation"):
        raw = evidence.get(key)
        if raw is None and isinstance(evidence.get("risk"), dict):
            raw = evidence["risk"].get(key)
        if raw is not None:
            try:
                return _d(raw)
            except Exception:  # noqa: BLE001
                return None
    return None


async def plan_from_decision(
    session: AsyncSession,
    *,
    account: PaperAccount,
    record: DecisionRecord,
    candidate_id: uuid.UUID | None = None,
) -> PaperPlan:
    if record.action != "ENTER":
        raise AppError(
            "PAPER_NOT_ENTER",
            f"Only ENTER decisions can open paper trades (got {record.action})",
            retryable=False,
        )
    if not record.risk_approved:
        raise AppError(
            "PAPER_RISK_VETO", "Decision was risk-vetoed; paper trade refused", retryable=False
        )
    if record.entry_price is None or record.stop_price is None or record.target_price is None:
        raise AppError(
            "PAPER_MISSING_PRICES",
            "Decision is missing entry/stop/target — refusing invent",
            retryable=False,
        )
    fill_model = dict(account.fill_model or default_fill_model())
    equity = _d(account.equity)
    qty, _notional, notes = paper_quantity(
        equity=equity,
        risk_pct=risk_pct(fill_model),
        entry=_d(record.entry_price),
        stop=_d(record.stop_price),
        instrument=None,
    )
    if qty is None or qty <= 0:
        raise AppError(
            "PAPER_SIZE_FAILED",
            "Could not size paper quantity: " + ", ".join(notes or ["unknown"]),
            retryable=False,
        )
    risk_amount = abs(_d(record.entry_price) - _d(record.stop_price)) * qty
    plan = PaperPlan(
        symbol=record.symbol,
        timeframe=record.timeframe,
        direction=record.direction,
        signal_bar_open_time=record.bar_open_time,
        planned_entry=_d(record.entry_price),
        stop_price=_d(record.stop_price),
        target_price=_d(record.target_price),
        invalidation_price=_invalidation_from_record(record),
        qty=qty,
        risk_amount=risk_amount,
        fill_model=fill_model,
        decision_record_id=str(record.id),
        candidate_id=None if candidate_id is None else str(candidate_id),
        notes=["PAPER", *notes],
    )
    blockers = validate_plan(plan)
    if blockers:
        raise AppError(
            "PAPER_PLAN_INVALID",
            "Paper plan failed validation: " + ", ".join(blockers),
            retryable=False,
            details={"blockers": blockers},
        )
    return plan


async def accept_decision(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    decision_record_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
) -> PaperTrade:
    if decision_record_id is None and candidate_id is None:
        raise AppError(
            "INVALID_REQUEST", "decision_record_id or candidate_id required", retryable=False
        )
    account = await ensure_paper_account(session, owner_user_id=owner_user_id)
    record: DecisionRecord | None = None
    resolved_candidate: uuid.UUID | None = candidate_id
    if candidate_id is not None:
        candidate = await session.get(SignalCandidate, candidate_id)
        if candidate is None or candidate.owner_user_id != owner_user_id:
            raise NotFoundError("Signal candidate not found")
        if candidate.decision_record_id is None:
            raise AppError(
                "PAPER_NO_DECISION", "Candidate has no decision record", retryable=False
            )
        decision_record_id = candidate.decision_record_id
    assert decision_record_id is not None
    record = await session.get(DecisionRecord, decision_record_id)
    if record is None or record.owner_user_id != owner_user_id:
        raise NotFoundError("Decision record not found")

    existing = await session.execute(
        select(PaperTrade).where(
            PaperTrade.decision_record_id == decision_record_id,
            PaperTrade.status.in_((STATUS_READY, STATUS_OPEN)),
        )
    )
    prior = existing.scalar_one_or_none()
    if prior is not None:
        return prior

    plan = await plan_from_decision(
        session, account=account, record=record, candidate_id=resolved_candidate
    )
    trade = PaperTrade(
        account_id=account.id,
        owner_user_id=owner_user_id,
        decision_record_id=decision_record_id,
        candidate_id=resolved_candidate,
        instrument_symbol=plan.symbol,
        timeframe=plan.timeframe,
        direction=plan.direction,
        status=STATUS_READY,
        label=PAPER_LABEL,
        signal_bar_open_time=plan.signal_bar_open_time,
        planned_entry=_f(plan.planned_entry),
        stop_price=_f(plan.stop_price),
        target_price=_f(plan.target_price),
        invalidation_price=_f(plan.invalidation_price),
        qty=_f(plan.qty),
        risk_amount=_f(plan.risk_amount),
        fill_model=plan.fill_model,
        notes=list(plan.notes),
    )
    session.add(trade)
    await session.flush()
    await _emit(
        session,
        trade_id=trade.id,
        event_type="accepted",
        bar_open_time=plan.signal_bar_open_time,
        payload={"status": STATUS_READY, "label": PAPER_LABEL, "notes": plan.notes},
    )
    session.add(
        OutboxEvent(
            topic="paper.trade.accepted",
            aggregate_type="paper_trade",
            aggregate_id=trade.id,
            payload={
                "status": STATUS_READY,
                "symbol": trade.instrument_symbol,
                "timeframe": trade.timeframe,
                "label": PAPER_LABEL,
            },
        )
    )
    # Attempt immediate fill if the next candle already exists.
    await _advance_trade(session, trade=trade)
    await session.commit()
    loaded = await session.get(PaperTrade, trade.id)
    assert loaded is not None
    return loaded


async def cancel_trade(
    session: AsyncSession, *, owner_user_id: uuid.UUID, trade_id: uuid.UUID
) -> PaperTrade:
    trade = await session.get(PaperTrade, trade_id)
    if trade is None or trade.owner_user_id != owner_user_id:
        raise NotFoundError("Paper trade not found")
    if trade.status != STATUS_READY:
        raise AppError(
            "PAPER_NOT_CANCELLABLE",
            f"Only ready trades can be cancelled (status={trade.status})",
            retryable=False,
        )
    trade.status = STATUS_CANCELLED
    trade.closed_at = datetime.now(UTC)
    trade.exit_reason = "cancelled"
    await _emit(session, trade_id=trade.id, event_type="cancelled", payload={"label": PAPER_LABEL})
    await session.commit()
    return trade


async def _close_trade(
    session: AsyncSession,
    *,
    trade: PaperTrade,
    exit_price: Decimal,
    exit_reason: str,
    exit_bar: datetime,
    realized_pnl: Decimal,
    realized_r: Decimal,
    costs: Decimal,
    bars_held: int,
) -> None:
    account = await session.get(PaperAccount, trade.account_id)
    trade.status = STATUS_CLOSED
    trade.exit_price = _f(exit_price)
    trade.exit_reason = exit_reason
    trade.exit_bar_open_time = exit_bar
    trade.realized_pnl = _f(realized_pnl)
    trade.realized_r = _f(realized_r)
    trade.costs = _f(costs) or 0.0
    trade.bars_held = bars_held
    trade.closed_at = datetime.now(UTC)
    if account is not None:
        account.equity = float(_d(account.equity) + realized_pnl)
    await _emit(
        session,
        trade_id=trade.id,
        event_type="closed",
        bar_open_time=exit_bar,
        payload={
            "exit_reason": exit_reason,
            "exit_price": str(exit_price),
            "realized_r": str(realized_r),
            "realized_pnl": str(realized_pnl),
            "label": PAPER_LABEL,
        },
    )
    summary = journal_summary(
        symbol=trade.instrument_symbol,
        timeframe=trade.timeframe,
        direction=trade.direction,
        exit_reason=exit_reason,
        realized_r=realized_r,
        realized_pnl=realized_pnl,
    )
    journal = await create_paper_journal_entry(session, trade=trade, summary=summary)
    trade.journal_entry_id = journal.id
    session.add(
        OutboxEvent(
            topic="paper.trade.closed",
            aggregate_type="paper_trade",
            aggregate_id=trade.id,
            payload={
                "status": STATUS_CLOSED,
                "exit_reason": exit_reason,
                "realized_r": str(realized_r),
                "label": PAPER_LABEL,
                "journal_entry_id": str(journal.id),
            },
        )
    )


async def _advance_trade(session: AsyncSession, *, trade: PaperTrade) -> dict[str, Any]:
    after = trade.signal_bar_open_time
    if trade.status == STATUS_OPEN and trade.entry_bar_open_time is not None:
        after = trade.entry_bar_open_time
    bars = await load_bars_after(
        session,
        symbol=trade.instrument_symbol,
        timeframe=trade.timeframe,
        after=after,
    )
    if trade.status == STATUS_READY:
        fill = try_fill_at_next_open(
            signal_bar_open_time=trade.signal_bar_open_time,
            direction=trade.direction,
            fill_model=dict(trade.fill_model or {}),
            bars=bars,
        )
        if not fill.filled:
            return {"status": STATUS_READY, "note": fill.note}
        trade.status = STATUS_OPEN
        trade.entry_price = _f(fill.entry_price)
        trade.entry_bar_open_time = fill.entry_bar_open_time
        await _emit(
            session,
            trade_id=trade.id,
            event_type="filled",
            bar_open_time=fill.entry_bar_open_time,
            payload={
                "entry_price": str(fill.entry_price),
                "label": PAPER_LABEL,
                "note": fill.note,
            },
        )
        # Continue with management on subsequent bars in the same batch.
        bars = [b for b in bars if b.open_time > fill.entry_bar_open_time]  # type: ignore[operator]

    if (
        trade.status != STATUS_OPEN
        or trade.entry_price is None
        or trade.entry_bar_open_time is None
    ):
        return {"status": trade.status}

    fill_model = dict(trade.fill_model or {})
    entry = _d(trade.entry_price)
    stop = _d(trade.stop_price)
    target = _d(trade.target_price)
    invalidation = None if trade.invalidation_price is None else _d(trade.invalidation_price)
    qty = _d(trade.qty)
    bars_held = trade.bars_held
    for bar in bars:
        bars_held += 1
        trade.bars_held = bars_held
        outcome = evaluate_exit_on_bar(
            bar,
            direction=trade.direction,
            entry_price=entry,
            stop=stop,
            target=target,
            invalidation=invalidation,
            entry_bar_open_time=trade.entry_bar_open_time,
            fill_model=fill_model,
            qty=qty,
        )
        if not outcome.closed:
            timed = timeout_exit(
                bar,
                direction=trade.direction,
                entry_price=entry,
                stop=stop,
                fill_model=fill_model,
                qty=qty,
                bars_held=bars_held,
            )
            if timed is None:
                continue
            outcome = timed
        assert outcome.exit_price is not None and outcome.realized_pnl is not None
        assert outcome.realized_r is not None and outcome.exit_reason is not None
        assert outcome.exit_bar_open_time is not None
        await _close_trade(
            session,
            trade=trade,
            exit_price=outcome.exit_price,
            exit_reason=outcome.exit_reason,
            exit_bar=outcome.exit_bar_open_time,
            realized_pnl=outcome.realized_pnl,
            realized_r=outcome.realized_r,
            costs=outcome.costs,
            bars_held=bars_held,
        )
        return {"status": STATUS_CLOSED, "exit_reason": outcome.exit_reason}
    return {"status": trade.status, "bars_held": bars_held}


async def monitor_account(
    session: AsyncSession, *, owner_user_id: uuid.UUID | None = None
) -> dict[str, Any]:
    stmt = select(PaperTrade).where(PaperTrade.status.in_((STATUS_READY, STATUS_OPEN)))
    if owner_user_id is not None:
        stmt = stmt.where(PaperTrade.owner_user_id == owner_user_id)
    result = await session.execute(stmt.order_by(PaperTrade.created_at))
    trades = list(result.scalars().all())
    counts = {"ready": 0, "open": 0, "closed": 0, "unchanged": 0}
    for trade in trades:
        before = trade.status
        await _advance_trade(session, trade=trade)
        if trade.status == STATUS_CLOSED:
            counts["closed"] += 1
        elif trade.status == STATUS_OPEN and before == STATUS_READY:
            counts["open"] += 1
        elif trade.status == STATUS_READY:
            counts["ready"] += 1
        else:
            counts["unchanged"] += 1
    await session.commit()
    return {"processed": len(trades), **counts}


async def list_trades(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[PaperTrade]:
    stmt = select(PaperTrade).where(PaperTrade.owner_user_id == owner_user_id)
    if status:
        stmt = stmt.where(PaperTrade.status == status)
    stmt = stmt.order_by(PaperTrade.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_trade(
    session: AsyncSession, *, owner_user_id: uuid.UUID, trade_id: uuid.UUID
) -> PaperTrade | None:
    trade = await session.get(PaperTrade, trade_id)
    if trade is None or trade.owner_user_id != owner_user_id:
        return None
    return trade


async def list_events(
    session: AsyncSession, *, trade_id: uuid.UUID
) -> list[PaperTradeEvent]:
    result = await session.execute(
        select(PaperTradeEvent)
        .where(PaperTradeEvent.trade_id == trade_id)
        .order_by(PaperTradeEvent.created_at.asc())
    )
    return list(result.scalars().all())


def soak_status(account: PaperAccount, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    started = account.soak_started_at
    required = int(account.soak_days_required or 14)
    if started is None:
        return {
            "started": False,
            "days_elapsed": 0,
            "days_required": required,
            "complete": False,
            "label": PAPER_LABEL,
        }
    elapsed = max(0, (current - started).days)
    return {
        "started": True,
        "soak_started_at": started.isoformat(),
        "days_elapsed": elapsed,
        "days_required": required,
        "complete": elapsed >= required,
        "remaining_days": max(0, required - elapsed),
        "label": PAPER_LABEL,
        "note": (
            "Gate F: soak is complete only after required calendar days without "
            "integrity defects — operational sign-off still required before live alerts."
        ),
    }


async def account_summary(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    account = await ensure_paper_account(session, owner_user_id=owner_user_id)
    await session.commit()
    by_status = await session.execute(
        select(PaperTrade.status, func.count())
        .where(PaperTrade.account_id == account.id)
        .group_by(PaperTrade.status)
    )
    closed = await session.execute(
        select(func.count(), func.coalesce(func.sum(PaperTrade.realized_r), 0))
        .select_from(PaperTrade)
        .where(PaperTrade.account_id == account.id, PaperTrade.status == STATUS_CLOSED)
    )
    closed_count, sum_r = closed.one()
    integrity = await integrity_report(session, account_id=account.id)
    return {
        "account_id": str(account.id),
        "label": account.label,
        "currency": account.currency,
        "starting_equity": str(account.starting_equity),
        "equity": str(account.equity),
        "fill_model": dict(account.fill_model or {}),
        "trades_by_status": {str(k): int(v) for k, v in by_status.all()},
        "closed_trades": int(closed_count),
        "sum_realized_r": str(sum_r),
        "soak": soak_status(account),
        "integrity": integrity,
    }


async def integrity_report(
    session: AsyncSession, *, account_id: uuid.UUID
) -> dict[str, Any]:
    """Fail closed on state defects that would block Gate F."""
    defects: list[str] = []
    openish = await session.execute(
        select(PaperTrade).where(
            PaperTrade.account_id == account_id,
            PaperTrade.status.in_((STATUS_READY, STATUS_OPEN, STATUS_CLOSED)),
        )
    )
    for trade in openish.scalars().all():
        if trade.label != PAPER_LABEL:
            defects.append(f"{trade.id}:missing_PAPER_label")
        if trade.status == STATUS_OPEN and trade.entry_price is None:
            defects.append(f"{trade.id}:open_without_entry")
        if trade.status == STATUS_CLOSED:
            if trade.exit_price is None or trade.exit_reason is None:
                defects.append(f"{trade.id}:closed_incomplete")
            if trade.journal_entry_id is None:
                defects.append(f"{trade.id}:closed_without_journal")
        if trade.status == STATUS_READY and trade.entry_price is not None:
            defects.append(f"{trade.id}:ready_with_entry")
    return {
        "ok": len(defects) == 0,
        "defects": defects,
        "checked_at": datetime.now(UTC).isoformat(),
    }
