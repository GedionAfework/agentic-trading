from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from private_trading_core.config import get_settings
from private_trading_db.models.identity import UserRole
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.models.ops import OutboxEvent, SystemSetting
from private_trading_db.models.scanner import ScanRun, SignalCandidate
from private_trading_features.types import CandleBar
from private_trading_market_data.catalog import list_enabled_instruments
from private_trading_market_data.health import instrument_snapshot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_agents.scanner import (
    SCANNER_VERSION,
    ScanOutcome,
    candidate_payload,
    evaluate_closed_candle,
)
from private_trading_agents.service import persist_decision

SWITCH_KEYS = ("scanner_enabled", "notifications_enabled")
QUEUES = ("market", "ai", "notifications", "backtests")


async def get_kill_switches(session: AsyncSession) -> dict[str, bool]:
    settings = get_settings()
    values = {
        "scanner_enabled": settings.scanner_enabled,
        "notifications_enabled": settings.notifications_enabled,
    }
    result = await session.execute(select(SystemSetting).where(SystemSetting.key.in_(SWITCH_KEYS)))
    for row in result.scalars().all():
        if isinstance(row.value, dict) and "enabled" in row.value:
            values[row.key] = bool(row.value["enabled"])
    return values


async def set_kill_switch(
    session: AsyncSession, *, key: str, enabled: bool, actor_user_id: uuid.UUID | None
) -> dict[str, bool]:
    if key not in SWITCH_KEYS:
        raise ValueError(f"unknown switch {key}")
    row = await session.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value={"enabled": enabled}, updated_by=actor_user_id)
        session.add(row)
    else:
        row.value = {"enabled": enabled}
        row.updated_by = actor_user_id
    await session.commit()
    return await get_kill_switches(session)


async def resolve_owner_user_id(session: AsyncSession) -> uuid.UUID | None:
    result = await session.execute(
        select(UserRole.user_id).where(UserRole.role == "owner").limit(1)
    )
    return result.scalar_one_or_none()


async def load_final_bars(
    session: AsyncSession, *, instrument_id: uuid.UUID, timeframe: str, limit: int = 200
) -> list[CandleBar]:
    result = await session.execute(
        select(Candle)
        .where(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
            Candle.is_final.is_(True),
        )
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return [
        CandleBar(
            open_time=row.open_time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            is_final=True,
        )
        for row in rows
    ]


async def _existing_run(
    session: AsyncSession, *, symbol: str, timeframe: str, candle_open_time: datetime
) -> ScanRun | None:
    result = await session.execute(
        select(ScanRun).where(
            ScanRun.instrument_symbol == symbol,
            ScanRun.timeframe == timeframe,
            ScanRun.candle_open_time == candle_open_time,
        )
    )
    return result.scalar_one_or_none()


async def _register_candidate(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    symbol: str,
    timeframe: str,
    outcome: ScanOutcome,
    notifications_enabled: bool,
) -> tuple[SignalCandidate, bool]:
    assert outcome.snapshot is not None and outcome.dedupe_key is not None
    result = await session.execute(
        select(SignalCandidate).where(SignalCandidate.dedupe_key == outcome.dedupe_key)
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.seen_count += 1
        existing.last_seen_at = now
        await session.flush()
        return existing, False

    record = await persist_decision(session, owner_user_id=owner_user_id, snapshot=outcome.snapshot)
    publish_state = "published" if notifications_enabled else "suppressed_kill_switch"
    candidate = SignalCandidate(
        owner_user_id=owner_user_id,
        dedupe_key=outcome.dedupe_key,
        strategy_code=outcome.snapshot.strategy_code,
        strategy_version_no=outcome.snapshot.strategy_version_no,
        instrument_symbol=symbol,
        timeframe=timeframe,
        setup_anchor=outcome.setup_anchor or "",
        signal_type=outcome.signal_type or "",
        action=outcome.snapshot.action.value,
        candle_open_time=outcome.snapshot.bar_open_time,
        decision_record_id=record.id,
        publish_state=publish_state,
        payload=candidate_payload(outcome.snapshot),
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(candidate)
    await session.flush()
    if notifications_enabled:
        session.add(
            OutboxEvent(
                topic="signal.candidate",
                aggregate_type="signal_candidate",
                aggregate_id=candidate.id,
                payload={
                    "dedupe_key": candidate.dedupe_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "action": candidate.action,
                    "decision_record_id": str(record.id),
                    "confidence_band": outcome.snapshot.confidence_band,
                },
            )
        )
    return candidate, True


async def scan_instrument_timeframe(
    session: AsyncSession,
    *,
    instrument: Instrument,
    timeframe: str,
    owner_user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> ScanRun | dict[str, Any]:
    started = perf_counter()
    switches = await get_kill_switches(session)
    symbol = instrument.canonical_symbol
    if not switches["scanner_enabled"]:
        return {"instrument_symbol": symbol, "timeframe": timeframe, "status": "skipped_disabled"}

    bars = await load_final_bars(session, instrument_id=instrument.id, timeframe=timeframe)
    if not bars:
        return {"instrument_symbol": symbol, "timeframe": timeframe, "status": "skipped_no_data"}
    candle_open_time = bars[-1].open_time
    prior = await _existing_run(
        session, symbol=symbol, timeframe=timeframe, candle_open_time=candle_open_time
    )
    if prior is not None:
        return prior

    snapshot = await instrument_snapshot(
        session, instrument=instrument, timeframe=timeframe, now=now
    )
    run = ScanRun(
        instrument_symbol=symbol,
        timeframe=timeframe,
        candle_open_time=candle_open_time,
        status="failed",
        fresh=snapshot.fresh,
        actionable=snapshot.actionable,
        details={"quality_flags": snapshot.quality_flags, "scanner_version": SCANNER_VERSION},
    )
    try:
        outcome = evaluate_closed_candle(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            fresh=snapshot.fresh,
            actionable=snapshot.actionable,
        )
        run.status = outcome.status
        run.action = outcome.action
        run.setup_state = outcome.setup_state
        run.details["notes"] = outcome.notes
        if outcome.publishable:
            owner = owner_user_id or await resolve_owner_user_id(session)
            if owner is None:
                run.status = "failed"
                run.error = "no_owner_user_for_candidate"
            else:
                candidate, is_new = await _register_candidate(
                    session,
                    owner_user_id=owner,
                    symbol=symbol,
                    timeframe=timeframe,
                    outcome=outcome,
                    notifications_enabled=switches["notifications_enabled"],
                )
                run.candidate_id = candidate.id
                run.candidate_new = is_new
                run.details["publish_state"] = candidate.publish_state
    except Exception as exc:  # noqa: BLE001 — dead-letter the run, keep scanning others
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
    run.duration_ms = int((perf_counter() - started) * 1000)
    session.add(run)
    await session.commit()
    return run


async def scan_all(
    session: AsyncSession,
    *,
    timeframes: tuple[str, ...],
    owner_user_id: uuid.UUID | None = None,
    symbols: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    instruments = await list_enabled_instruments(session)
    summaries: list[dict[str, Any]] = []
    for instrument in instruments:
        if symbols and instrument.canonical_symbol not in symbols:
            continue
        for timeframe in timeframes:
            result = await scan_instrument_timeframe(
                session, instrument=instrument, timeframe=timeframe, owner_user_id=owner_user_id
            )
            summaries.append(run_summary(result))
    return summaries


def run_summary(result: ScanRun | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {
        "id": str(result.id),
        "instrument_symbol": result.instrument_symbol,
        "timeframe": result.timeframe,
        "candle_open_time": result.candle_open_time.isoformat(),
        "status": result.status,
        "action": result.action,
        "setup_state": result.setup_state,
        "fresh": result.fresh,
        "actionable": result.actionable,
        "candidate_id": None if result.candidate_id is None else str(result.candidate_id),
        "candidate_new": result.candidate_new,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


async def queue_depths(redis_url: str) -> dict[str, int | None]:
    try:
        import redis.asyncio as aioredis
    except ImportError:  # pragma: no cover
        return {name: None for name in QUEUES}
    client = aioredis.from_url(redis_url, socket_connect_timeout=1.5, socket_timeout=1.5)
    try:
        return {name: int(await client.llen(name)) for name in QUEUES}
    except Exception:  # noqa: BLE001 — broker down is a status, not a crash
        return {name: None for name in QUEUES}
    finally:
        await client.aclose()


async def scanner_status(session: AsyncSession, *, timeframes: tuple[str, ...]) -> dict[str, Any]:
    switches = await get_kill_switches(session)
    latest_rows = await session.execute(
        select(ScanRun).order_by(ScanRun.created_at.desc()).limit(500)
    )
    runs = list(latest_rows.scalars().all())
    last_by_key: dict[str, dict[str, Any]] = {}
    last_success_by_key: dict[str, str] = {}
    for run in runs:
        key = f"{run.instrument_symbol}:{run.timeframe}"
        if key not in last_by_key:
            last_by_key[key] = run_summary(run)
        if run.status not in {"failed"} and key not in last_success_by_key:
            last_success_by_key[key] = run.created_at.isoformat()
    failed = await session.execute(
        select(func.count()).select_from(ScanRun).where(ScanRun.status == "failed")
    )
    candidates = await session.execute(select(func.count()).select_from(SignalCandidate))
    published = await session.execute(
        select(func.count())
        .select_from(SignalCandidate)
        .where(SignalCandidate.publish_state == "published")
    )
    return {
        "scanner_version": SCANNER_VERSION,
        "switches": switches,
        "timeframes": list(timeframes),
        "queues": await queue_depths(get_settings().redis_url),
        "last_run": last_by_key,
        "last_success": last_success_by_key,
        "dead_letters": int(failed.scalar_one()),
        "candidates_total": int(candidates.scalar_one()),
        "candidates_published": int(published.scalar_one()),
    }


async def list_candidates(session: AsyncSession, *, limit: int = 50) -> list[SignalCandidate]:
    result = await session.execute(
        select(SignalCandidate).order_by(SignalCandidate.last_seen_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
