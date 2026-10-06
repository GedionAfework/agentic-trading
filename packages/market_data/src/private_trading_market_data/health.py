from __future__ import annotations

from datetime import UTC, datetime

from private_trading_db.models.market import Candle, Instrument, MarketDataGap
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_market_data.contracts import MarketSnapshot, SUPPORTED_TIMEFRAMES
from private_trading_market_data.quality import actionable_for_signals, is_fresh
from private_trading_market_data.sessions import is_market_open


async def instrument_snapshot(
    session: AsyncSession,
    *,
    instrument: Instrument,
    timeframe: str,
    now: datetime | None = None,
) -> MarketSnapshot:
    current = now or datetime.now(UTC)
    last_result = await session.execute(
        select(Candle)
        .where(Candle.instrument_id == instrument.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(1)
    )
    last = last_result.scalar_one_or_none()

    count_result = await session.execute(
        select(func.count())
        .select_from(Candle)
        .where(Candle.instrument_id == instrument.id, Candle.timeframe == timeframe)
    )
    candle_count = int(count_result.scalar_one())

    gaps_result = await session.execute(
        select(func.count())
        .select_from(MarketDataGap)
        .where(
            MarketDataGap.instrument_id == instrument.id,
            MarketDataGap.timeframe == timeframe,
            MarketDataGap.status == "open",
        )
    )
    gaps_open = int(gaps_result.scalar_one())

    quality_flags: list[str] = []
    if last is not None and isinstance(last.quality_flags, list):
        quality_flags.extend(str(f) for f in last.quality_flags)

    fresh = is_fresh(timeframe=timeframe, last_open_time=last.open_time if last else None, now=current)
    if not fresh:
        quality_flags.append("stale")
    if not is_market_open(instrument.asset_class, current):
        quality_flags.append("market_closed")

    actionable = actionable_for_signals(
        fresh=fresh,
        open_gaps=gaps_open,
        quality_flags=quality_flags,
    ) and is_market_open(instrument.asset_class, current)

    return MarketSnapshot(
        instrument_symbol=instrument.canonical_symbol,
        timeframe=timeframe,
        as_of=current,
        last_open_time=last.open_time if last else None,
        last_close=last.close if last else None,
        candle_count=candle_count,
        fresh=fresh,
        actionable=actionable,
        quality_flags=sorted(set(quality_flags)),
        gaps_open=gaps_open,
    )


async def market_health(
    session: AsyncSession,
    *,
    timeframes: tuple[str, ...] = ("15m", "1h"),
) -> list[MarketSnapshot]:
    result = await session.execute(
        select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.canonical_symbol)
    )
    instruments = list(result.scalars().all())
    snapshots: list[MarketSnapshot] = []
    for instrument in instruments:
        for timeframe in timeframes:
            if timeframe not in SUPPORTED_TIMEFRAMES:
                continue
            snapshots.append(
                await instrument_snapshot(session, instrument=instrument, timeframe=timeframe)
            )
    return snapshots
