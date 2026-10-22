"""Paper account / trade persistence and monitoring against closed candles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from private_trading_core.errors import AppError, NotFoundError
from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.models.ops import OutboxEvent, SystemSetting
from private_trading_db.models.paper import PaperAccount, PaperTrade, PaperTradeEvent
from private_trading_db.models.scanner import SignalCandidate
from private_trading_features.types import CandleBar
from private_trading_journal.service import create_paper_journal_entry
from private_trading_risk.portfolio import (
    OpenExposure,
    PortfolioRiskInput,
    assess_portfolio_risk,
)
from private_trading_risk.sizing import paper_quantity
from private_trading_strategies.soak_freeze import (
    SOAK_FILL_MODEL,
    SOAK_RESEARCH_MEAN_R,
    SOAK_RESEARCH_WIN_RATE,
    SOAK_STEP1_MIN_CLOSED_TRADES,
    SOAK_STEP2_MAX_DRAWDOWN_R,
    SOAK_STEP2_MAX_EXTRA_COST_BPS,
    SOAK_STEP2_MIN_CLOSED_TRADES,
    SOAK_STEP2_MIN_MEAN_R,
    SOAK_STEP2_MIN_POSITIVE_MONTH_FRACTION,
    SOAK_STEP2_MIN_PROFIT_FACTOR,
    SOAK_STEP2_MIN_TRADES_PER_MONTH,
    SOAK_SYMBOL,
    soak_incumbent,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_paper_trade.engine import (
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_READY,
    PaperPlan,
    ScaleOutState,
    evaluate_exit_on_bar,
    evaluate_scale_out_on_bar,
    journal_summary,
    timeout_exit,
    try_fill_at_next_open,
    validate_plan,
)
from private_trading_paper_trade.fill_model import (
    PAPER_LABEL,
    default_fill_model,
    risk_pct,
    soak_fill_diagnostics,
)
from private_trading_paper_trade.holdout import evaluate_holdout_review
from private_trading_paper_trade.live_alert_gate import evaluate_live_alert_decision
from private_trading_paper_trade.promotion import evaluate_paper_promotion
from private_trading_paper_trade.soak_metrics import ClosedSoakTrade, evaluate_soak_sample

SOAK_LIVE_ALERT_OWNER_UNLOCK_KEY = "soak_live_alert_owner_unlock"

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
    if record.symbol == SOAK_SYMBOL:
        notes = list(fill_model.get("notes") or [])
        soak_notes = list(SOAK_FILL_MODEL.get("notes") or [])
        fill_model.update(
            {key: value for key, value in SOAK_FILL_MODEL.items() if key != "notes"}
        )
        fill_model["notes"] = notes + [note for note in soak_notes if note not in notes]
        fill_model["soak_freeze_model"] = soak_incumbent().code
    exposures, daily_pnl = await paper_portfolio_state(
        session, owner_user_id=account.owner_user_id
    )
    asset_class = "crypto" if record.symbol.endswith("/USDT") else "forex"
    portfolio = assess_portfolio_risk(
        PortfolioRiskInput(
            proposed_symbol=record.symbol,
            proposed_asset_class=asset_class,
            proposed_direction=record.direction,
            proposed_risk_pct=risk_pct(fill_model),
            open_exposures=exposures,
            daily_realized_pnl_pct=daily_pnl,
        )
    )
    if not portfolio.approved:
        raise AppError(
            "PAPER_PORTFOLIO_VETO",
            "Paper trade refused by portfolio risk: " + ", ".join(portfolio.blockers),
            retryable=False,
            details={"blockers": portfolio.blockers},
        )
    paper_model = dict(record.evidence or {}).get("paper_model")
    if isinstance(paper_model, dict):
        if not paper_model.get("paper_only") or paper_model.get("live_alerts_allowed"):
            raise AppError(
                "PAPER_MODEL_NOT_SAFE",
                "Model metadata does not enforce paper-only execution",
                retryable=False,
            )
        fill_model.update(
            {
                "paper_model_code": paper_model.get("code"),
                "paper_model_version": paper_model.get("version_no"),
                "partial_profit_at_r": paper_model.get("partial_profit_at_r"),
                "partial_profit_fraction": paper_model.get(
                    "partial_profit_fraction", 0
                ),
                "move_stop_to_breakeven_after_partial": paper_model.get(
                    "move_stop_to_breakeven_after_partial", False
                ),
                "original_stop_price": str(record.stop_price),
                "max_bars_in_trade": paper_model.get(
                    "max_bars_in_trade",
                    fill_model.get("max_bars_in_trade", 20),
                ),
                "live_alerts_allowed": False,
            }
        )
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
    fill_model = dict(trade.fill_model or {})
    soak = dict(fill_model.get("soak_fill") or {})
    journal = await create_paper_journal_entry(
        session,
        trade=trade,
        summary=summary,
        details={
            "signal_bar_open_time": trade.signal_bar_open_time.isoformat(),
            "entry_bar_open_time": (
                None
                if trade.entry_bar_open_time is None
                else trade.entry_bar_open_time.isoformat()
            ),
            "paper_model_code": fill_model.get("paper_model_code"),
            "exit_reason": exit_reason,
            "realized_r": str(realized_r),
            **soak,
        },
    )
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
        diagnostics = soak_fill_diagnostics(
            direction=trade.direction,
            planned_entry=_d(trade.planned_entry),
            raw_open=fill.raw_open,
            filled_price=_d(fill.entry_price),
            fill_model=dict(trade.fill_model or {}),
        )
        merged = dict(trade.fill_model or {})
        merged["soak_fill"] = diagnostics
        trade.fill_model = merged
        await _emit(
            session,
            trade_id=trade.id,
            event_type="filled",
            bar_open_time=fill.entry_bar_open_time,
            payload={
                "entry_price": str(fill.entry_price),
                "raw_open": None if fill.raw_open is None else str(fill.raw_open),
                "label": PAPER_LABEL,
                "note": fill.note,
                "soak_fill": diagnostics,
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
        last_managed = fill_model.get("last_managed_bar")
        if last_managed and bar.open_time.isoformat() <= str(last_managed):
            continue
        bars_held += 1
        trade.bars_held = bars_held
        partial_at = fill_model.get("partial_profit_at_r")
        partial_fraction = _d(fill_model.get("partial_profit_fraction") or 0)
        if partial_at is not None and Decimal("0") < partial_fraction < Decimal("1"):
            stored_state = dict(fill_model.get("scale_out_state") or {})
            state = ScaleOutState(
                remaining_qty=_d(stored_state.get("remaining_qty", qty)),
                current_stop=_d(stored_state.get("current_stop", stop)),
                realized_pnl=_d(stored_state.get("realized_pnl", 0)),
                costs=_d(stored_state.get("costs", 0)),
                partial_taken=bool(stored_state.get("partial_taken", False)),
            )
            managed = evaluate_scale_out_on_bar(
                bar,
                direction=trade.direction,
                entry_price=entry,
                original_stop=_d(fill_model.get("original_stop_price", stop)),
                runner_target=target,
                partial_at_r=_d(partial_at),
                partial_fraction=partial_fraction,
                move_stop_to_breakeven=bool(
                    fill_model.get("move_stop_to_breakeven_after_partial")
                ),
                invalidation=invalidation,
                entry_bar_open_time=trade.entry_bar_open_time,
                fill_model=fill_model,
                original_qty=qty,
                state=state,
                bars_held=bars_held,
            )
            fill_model["scale_out_state"] = {
                "remaining_qty": str(managed.state.remaining_qty),
                "current_stop": str(managed.state.current_stop),
                "realized_pnl": str(managed.state.realized_pnl),
                "costs": str(managed.state.costs),
                "partial_taken": managed.state.partial_taken,
            }
            fill_model["last_managed_bar"] = bar.open_time.isoformat()
            trade.fill_model = dict(fill_model)
            trade.stop_price = _f(managed.state.current_stop)
            if managed.event == "partial_profit":
                await _emit(
                    session,
                    trade_id=trade.id,
                    event_type="partial_profit",
                    bar_open_time=bar.open_time,
                    payload={
                        "remaining_qty": str(managed.state.remaining_qty),
                        "stop_price": str(managed.state.current_stop),
                        "label": PAPER_LABEL,
                    },
                )
            outcome = managed.outcome
            if not outcome.closed:
                continue
        else:
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


async def paper_portfolio_state(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID | None,
) -> tuple[tuple[OpenExposure, ...], Decimal]:
    if owner_user_id is None:
        return (), Decimal("0")
    open_rows = await session.execute(
        select(PaperTrade).where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status.in_((STATUS_READY, STATUS_OPEN)),
        )
    )
    exposures = tuple(
        OpenExposure(
            symbol=row.instrument_symbol,
            asset_class="crypto" if row.instrument_symbol.endswith("/USDT") else "forex",
            direction=row.direction,
            risk_pct=risk_pct(dict(row.fill_model or default_fill_model())),
        )
        for row in open_rows.scalars().all()
    )
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    closed = await session.execute(
        select(func.coalesce(func.sum(PaperTrade.realized_pnl), 0)).where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status == STATUS_CLOSED,
            PaperTrade.closed_at >= start,
        )
    )
    pnl = _d(closed.scalar_one())
    account = await get_account(session, owner_user_id=owner_user_id)
    equity = _d(account.starting_equity) if account is not None else Decimal("0")
    daily_pct = (pnl / equity * Decimal("100")) if equity > 0 else Decimal("0")
    return exposures, daily_pct


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
        "soak_step1": await soak_step1_progress(session, owner_user_id=owner_user_id),
        "soak_step2": await soak_step2_progress(session, owner_user_id=owner_user_id),
        "soak_step3": await soak_step3_progress(session, owner_user_id=owner_user_id),
        "soak_step4": await soak_step4_progress(session, owner_user_id=owner_user_id),
        "soak_step5": await soak_step5_progress(session, owner_user_id=owner_user_id),
        "integrity": integrity,
    }


async def _closed_soak_trades(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[ClosedSoakTrade]:
    rows = await session.execute(
        select(PaperTrade).where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.instrument_symbol == SOAK_SYMBOL,
            PaperTrade.status == STATUS_CLOSED,
        )
    )
    closed: list[ClosedSoakTrade] = []
    for trade in rows.scalars().all():
        if trade.realized_r is None:
            continue
        extra = dict(trade.fill_model or {}).get("soak_fill", {}).get(
            "extra_cost_bps_vs_research"
        )
        closed.append(
            ClosedSoakTrade(
                realized_r=float(trade.realized_r),
                closed_at=trade.closed_at or trade.exit_bar_open_time,
                extra_cost_bps_vs_research=(
                    None if extra is None else float(extra)
                ),
            )
        )
    return closed


async def soak_step1_progress(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    sample = evaluate_soak_sample(
        await _closed_soak_trades(session, owner_user_id=owner_user_id),
        min_closed_trades=SOAK_STEP1_MIN_CLOSED_TRADES,
        min_mean_r=0.0,
        min_profit_factor=1.0,
        max_drawdown_r_limit=SOAK_STEP2_MAX_DRAWDOWN_R,
        min_positive_month_fraction=0.0,
        min_trades_per_month=1,
        max_extra_cost_bps=SOAK_STEP2_MAX_EXTRA_COST_BPS,
        research_mean_r=SOAK_RESEARCH_MEAN_R,
        research_win_rate=SOAK_RESEARCH_WIN_RATE,
    )
    trades = int(sample["closed_trades"])
    mean_r = float(sample["mean_r"])
    return {
        "symbol": SOAK_SYMBOL,
        "closed_trades": trades,
        "min_closed_trades": SOAK_STEP1_MIN_CLOSED_TRADES,
        "win_rate": sample["win_rate"],
        "mean_r": mean_r,
        "max_drawdown_r": sample["max_drawdown_r"],
        "avg_extra_cost_bps_vs_research": sample["avg_extra_cost_bps_vs_research"],
        "research_mean_r": SOAK_RESEARCH_MEAN_R,
        "research_win_rate": SOAK_RESEARCH_WIN_RATE,
        "step1_complete": trades >= SOAK_STEP1_MIN_CLOSED_TRADES,
        "continue_soak": trades >= SOAK_STEP1_MIN_CLOSED_TRADES and mean_r > 0,
    }


async def soak_step2_progress(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    sample = evaluate_soak_sample(
        await _closed_soak_trades(session, owner_user_id=owner_user_id),
        min_closed_trades=SOAK_STEP2_MIN_CLOSED_TRADES,
        min_mean_r=SOAK_STEP2_MIN_MEAN_R,
        min_profit_factor=SOAK_STEP2_MIN_PROFIT_FACTOR,
        max_drawdown_r_limit=SOAK_STEP2_MAX_DRAWDOWN_R,
        min_positive_month_fraction=SOAK_STEP2_MIN_POSITIVE_MONTH_FRACTION,
        min_trades_per_month=SOAK_STEP2_MIN_TRADES_PER_MONTH,
        max_extra_cost_bps=SOAK_STEP2_MAX_EXTRA_COST_BPS,
        research_mean_r=SOAK_RESEARCH_MEAN_R,
        research_win_rate=SOAK_RESEARCH_WIN_RATE,
    )
    return {
        "symbol": SOAK_SYMBOL,
        "model_code": soak_incumbent().code,
        "objective": soak_incumbent().objective.value,
        **sample,
        "step2_complete": bool(sample["all_gates_passed"]),
        "ready_for_holdout_review": bool(sample["all_gates_passed"]),
        "note": (
            "Step 2 uses only closed SOL paper trades on the frozen V1 model. "
            "Do not retune 2022–2026 to pass these gates."
        ),
    }


async def soak_step3_progress(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    step2 = await soak_step2_progress(session, owner_user_id=owner_user_id)
    return evaluate_holdout_review(
        await _closed_soak_trades(session, owner_user_id=owner_user_id),
        step2_complete=bool(step2["step2_complete"]),
    )


async def soak_step4_progress(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    return evaluate_paper_promotion(
        await soak_step3_progress(session, owner_user_id=owner_user_id)
    )


async def _owner_live_alert_unlock(session: AsyncSession) -> bool:
    row = await session.get(SystemSetting, SOAK_LIVE_ALERT_OWNER_UNLOCK_KEY)
    if row is None or not isinstance(row.value, dict):
        return False
    return bool(row.value.get("enabled"))


async def soak_step5_progress(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    # Owner unlock is a global system setting; step4 still uses this account.
    return evaluate_live_alert_decision(
        await soak_step4_progress(session, owner_user_id=owner_user_id),
        owner_unlock=await _owner_live_alert_unlock(session),
    )


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
