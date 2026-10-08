from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.analytics import (
    CalibrationSnapshot,
    FeedbackReviewItem,
    PerformanceSnapshot,
)
from private_trading_db.models.backtest import BacktestDataset, BacktestJob
from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.paper import PaperTrade
from private_trading_db.models.telegram import TelegramAlertAction
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_analytics.calibration import calibrate_bands
from private_trading_analytics.metrics import TradeRow, build_slices, session_bucket
from private_trading_analytics.narrate import narrate_calibration, narrate_performance
from private_trading_analytics.similar import find_similar_setups

ALLOWED_COHORTS = frozenset({"paper", "backtest"})


def _won_from_r(realized_r: float | None) -> bool | None:
    if realized_r is None:
        return None
    return realized_r > 0


async def _paper_trade_rows(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[TradeRow]:
    result = await session.execute(
        select(PaperTrade, DecisionRecord)
        .outerjoin(DecisionRecord, DecisionRecord.id == PaperTrade.decision_record_id)
        .where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status == "closed",
            PaperTrade.label == "PAPER",
        )
    )
    rows: list[TradeRow] = []
    for trade, decision in result.all():
        strategy = decision.strategy_code if decision is not None else "unknown"
        r = None if trade.realized_r is None else float(trade.realized_r)
        rows.append(
            TradeRow(
                strategy_code=strategy,
                instrument_symbol=trade.instrument_symbol,
                timeframe=trade.timeframe,
                session_bucket=session_bucket(
                    trade.entry_bar_open_time or trade.signal_bar_open_time
                ),
                direction=trade.direction,
                exit_reason=trade.exit_reason,
                realized_r=r,
                realized_pnl=None if trade.realized_pnl is None else float(trade.realized_pnl),
                won=_won_from_r(r),
            )
        )
    return rows


async def _backtest_trade_rows(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[TradeRow]:
    result = await session.execute(
        select(BacktestJob, BacktestDataset)
        .join(BacktestDataset, BacktestDataset.id == BacktestJob.dataset_id)
        .where(
            BacktestJob.owner_user_id == owner_user_id,
            BacktestJob.status == "completed",
        )
    )
    rows: list[TradeRow] = []
    for job, dataset in result.all():
        report = job.report or {}
        trades = report.get("trades") or []
        if not isinstance(trades, list):
            continue
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            r_raw = trade.get("realized_r")
            r = None if r_raw is None else float(r_raw)
            rows.append(
                TradeRow(
                    strategy_code=job.strategy_code,
                    instrument_symbol=dataset.symbol,
                    timeframe=dataset.timeframe,
                    session_bucket="unknown",
                    direction=str(trade.get("direction") or "unknown"),
                    exit_reason=str(trade.get("exit_reason") or trade.get("reason") or "unknown"),
                    realized_r=r,
                    realized_pnl=(
                        None if trade.get("realized_pnl") is None else float(trade["realized_pnl"])
                    ),
                    won=_won_from_r(r),
                )
            )
    return rows


async def _paper_calibration_obs(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(PaperTrade, DecisionRecord)
        .outerjoin(DecisionRecord, DecisionRecord.id == PaperTrade.decision_record_id)
        .where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status == "closed",
        )
    )
    obs: list[dict[str, Any]] = []
    for trade, decision in result.all():
        r = None if trade.realized_r is None else float(trade.realized_r)
        obs.append(
            {
                "confidence_band": (
                    decision.confidence_band if decision is not None else "unknown"
                ),
                "model_band": decision.model_band if decision is not None else "unknown",
                "realized_r": r,
                "won": _won_from_r(r),
            }
        )
    return obs


async def refresh_performance(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    cohort: str,
) -> list[PerformanceSnapshot]:
    if cohort not in ALLOWED_COHORTS:
        raise AppError(
            "INVALID_INPUT",
            f"cohort must be one of {sorted(ALLOWED_COHORTS)}; cohorts are never merged",
            retryable=False,
        )
    if cohort == "paper":
        trade_rows = await _paper_trade_rows(session, owner_user_id=owner_user_id)
    else:
        trade_rows = await _backtest_trade_rows(session, owner_user_id=owner_user_id)

    await session.execute(
        delete(PerformanceSnapshot).where(
            PerformanceSnapshot.owner_user_id == owner_user_id,
            PerformanceSnapshot.cohort == cohort,
        )
    )
    now = datetime.now(UTC)
    snapshots: list[PerformanceSnapshot] = []
    for slice_row in build_slices(trade_rows):
        snap = PerformanceSnapshot(
            owner_user_id=owner_user_id,
            cohort=cohort,
            grain=slice_row["grain"],
            strategy_code=slice_row["strategy_code"],
            instrument_symbol=slice_row["instrument_symbol"],
            timeframe=slice_row["timeframe"],
            session_bucket=slice_row["session_bucket"],
            sample_size=slice_row["sample_size"],
            sample_status=slice_row["sample_status"],
            metrics=slice_row["metrics"],
            warnings=slice_row["warnings"],
            computed_at=now,
        )
        session.add(snap)
        snapshots.append(snap)
    await session.flush()
    return snapshots


async def refresh_calibration(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    cohort: str = "paper",
    band_field: str = "confidence_band",
) -> CalibrationSnapshot:
    if cohort != "paper":
        raise AppError(
            "INVALID_INPUT",
            "Calibration v1 uses paper outcomes only (never merged with backtest)",
            retryable=False,
        )
    if band_field not in {"confidence_band", "model_band"}:
        raise AppError("INVALID_INPUT", "Unsupported band_field", retryable=False)
    obs = await _paper_calibration_obs(session, owner_user_id=owner_user_id)
    computed = calibrate_bands(obs, band_field=band_field)
    await session.execute(
        delete(CalibrationSnapshot).where(
            CalibrationSnapshot.owner_user_id == owner_user_id,
            CalibrationSnapshot.cohort == cohort,
            CalibrationSnapshot.band_field == band_field,
        )
    )
    snap = CalibrationSnapshot(
        owner_user_id=owner_user_id,
        cohort=cohort,
        band_field=band_field,
        sample_size=computed["sample_size"],
        sample_status=computed["sample_status"],
        bands=computed["bands"],
        drift_flags=computed["drift_flags"],
        warnings=computed["warnings"],
        computed_at=datetime.now(UTC),
    )
    session.add(snap)
    await session.flush()
    return snap


async def list_performance(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    cohort: str | None = None,
    grain: str | None = None,
) -> list[PerformanceSnapshot]:
    stmt = select(PerformanceSnapshot).where(
        PerformanceSnapshot.owner_user_id == owner_user_id
    )
    if cohort:
        if cohort not in ALLOWED_COHORTS:
            raise AppError("INVALID_INPUT", "Unknown cohort", retryable=False)
        stmt = stmt.where(PerformanceSnapshot.cohort == cohort)
    if grain:
        stmt = stmt.where(PerformanceSnapshot.grain == grain)
    stmt = stmt.order_by(
        PerformanceSnapshot.cohort,
        PerformanceSnapshot.grain,
        PerformanceSnapshot.computed_at.desc(),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_performance(
    session: AsyncSession, *, snapshot_id: uuid.UUID, owner_user_id: uuid.UUID
) -> PerformanceSnapshot | None:
    result = await session.execute(
        select(PerformanceSnapshot).where(
            PerformanceSnapshot.id == snapshot_id,
            PerformanceSnapshot.owner_user_id == owner_user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_calibration(
    session: AsyncSession, *, owner_user_id: uuid.UUID, cohort: str | None = "paper"
) -> list[CalibrationSnapshot]:
    stmt = select(CalibrationSnapshot).where(
        CalibrationSnapshot.owner_user_id == owner_user_id
    )
    if cohort:
        stmt = stmt.where(CalibrationSnapshot.cohort == cohort)
    stmt = stmt.order_by(CalibrationSnapshot.computed_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


def snapshot_to_dict(snap: PerformanceSnapshot) -> dict[str, Any]:
    return {
        "id": str(snap.id),
        "cohort": snap.cohort,
        "grain": snap.grain,
        "strategy_code": snap.strategy_code,
        "instrument_symbol": snap.instrument_symbol,
        "timeframe": snap.timeframe,
        "session_bucket": snap.session_bucket,
        "sample_size": snap.sample_size,
        "sample_status": snap.sample_status,
        "metrics": dict(snap.metrics or {}),
        "warnings": list(snap.warnings or []),
        "computed_at": snap.computed_at.isoformat() if snap.computed_at else None,
    }


def calibration_to_dict(snap: CalibrationSnapshot) -> dict[str, Any]:
    return {
        "id": str(snap.id),
        "cohort": snap.cohort,
        "band_field": snap.band_field,
        "sample_size": snap.sample_size,
        "sample_status": snap.sample_status,
        "bands": dict(snap.bands or {}),
        "drift_flags": list(snap.drift_flags or []),
        "warnings": list(snap.warnings or []),
        "computed_at": snap.computed_at.isoformat() if snap.computed_at else None,
    }


async def narrate_snapshot(
    session: AsyncSession, *, snapshot_id: uuid.UUID, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    snap = await get_performance(session, snapshot_id=snapshot_id, owner_user_id=owner_user_id)
    if snap is None:
        raise AppError("NOT_FOUND", "Performance snapshot not found", retryable=False)
    text = narrate_performance(snapshot_to_dict(snap))
    return {"snapshot_id": str(snap.id), "cohort": snap.cohort, "narrative": text}


async def narrate_calibration_snapshot(
    session: AsyncSession, *, snapshot_id: uuid.UUID, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    result = await session.execute(
        select(CalibrationSnapshot).where(
            CalibrationSnapshot.id == snapshot_id,
            CalibrationSnapshot.owner_user_id == owner_user_id,
        )
    )
    snap = result.scalar_one_or_none()
    if snap is None:
        raise AppError("NOT_FOUND", "Calibration snapshot not found", retryable=False)
    text = narrate_calibration(calibration_to_dict(snap))
    return {"snapshot_id": str(snap.id), "cohort": snap.cohort, "narrative": text}


async def sync_feedback_from_telegram(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[FeedbackReviewItem]:
    """Enqueue dismiss/skip/decision_taken alert actions that are not yet in the queue."""
    result = await session.execute(
        select(TelegramAlertAction).where(
            TelegramAlertAction.owner_user_id == owner_user_id,
            TelegramAlertAction.action.in_(("dismissed", "skipped", "decision_taken")),
        )
    )
    created: list[FeedbackReviewItem] = []
    for action in result.scalars().all():
        existing = await session.execute(
            select(FeedbackReviewItem).where(
                FeedbackReviewItem.source == "telegram_alert_action",
                FeedbackReviewItem.source_id == action.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        item = FeedbackReviewItem(
            owner_user_id=owner_user_id,
            source="telegram_alert_action",
            source_id=action.id,
            candidate_id=action.candidate_id,
            action=action.action,
            status="open",
            note=action.note,
            payload={},
        )
        session.add(item)
        created.append(item)
    await session.flush()
    return created


async def create_feedback(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    action: str,
    note: str | None,
    candidate_id: uuid.UUID | None,
    decision_record_id: uuid.UUID | None,
) -> FeedbackReviewItem:
    item = FeedbackReviewItem(
        owner_user_id=owner_user_id,
        source="manual",
        source_id=None,
        candidate_id=candidate_id,
        decision_record_id=decision_record_id,
        action=action,
        status="open",
        note=note,
        payload={},
    )
    session.add(item)
    await session.flush()
    return item


async def list_feedback(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    status: str | None = "open",
) -> list[FeedbackReviewItem]:
    stmt = select(FeedbackReviewItem).where(
        FeedbackReviewItem.owner_user_id == owner_user_id
    )
    if status:
        stmt = stmt.where(FeedbackReviewItem.status == status)
    stmt = stmt.order_by(FeedbackReviewItem.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def resolve_feedback(
    session: AsyncSession,
    *,
    item_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    resolver_id: uuid.UUID,
    resolution_note: str | None,
    status: str = "resolved",
) -> FeedbackReviewItem:
    result = await session.execute(
        select(FeedbackReviewItem).where(
            FeedbackReviewItem.id == item_id,
            FeedbackReviewItem.owner_user_id == owner_user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise AppError("NOT_FOUND", "Feedback item not found", retryable=False)
    if status not in {"resolved", "dismissed"}:
        raise AppError("INVALID_INPUT", "Invalid resolution status", retryable=False)
    item.status = status
    item.resolved_at = datetime.now(UTC)
    item.resolved_by = resolver_id
    item.resolution_note = resolution_note
    await session.flush()
    return item


async def similar_setups(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    candidate_id: uuid.UUID,
    limit: int = 10,
) -> dict[str, Any]:
    return await find_similar_setups(
        session, owner_user_id=owner_user_id, candidate_id=candidate_id, limit=limit
    )


async def performance_summary_for_telegram(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    snaps = await list_performance(
        session, owner_user_id=owner_user_id, cohort="paper", grain="overall"
    )
    if not snaps:
        await refresh_performance(session, owner_user_id=owner_user_id, cohort="paper")
        await session.commit()
        snaps = await list_performance(
            session, owner_user_id=owner_user_id, cohort="paper", grain="overall"
        )
    if not snaps:
        return {
            "cohort": "paper",
            "sample_size": 0,
            "sample_status": "insufficient_sample",
            "metrics": {},
            "warnings": ["No closed PAPER trades yet."],
            "narrative": None,
        }
    snap = snaps[0]
    data = snapshot_to_dict(snap)
    data["narrative"] = narrate_performance(data)
    return data
