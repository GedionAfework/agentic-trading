from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from private_trading_core.errors import AppError
from private_trading_db.models.market import Candle, MarketDataGap
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_market_data.catalog import (
    ensure_binance_catalog,
    get_instrument_by_symbol,
    get_provider_mapping,
)
from private_trading_market_data.contracts import SUPPORTED_TIMEFRAMES, NormalizedCandle
from private_trading_market_data.protocol import MarketDataProvider
from private_trading_market_data.quality import (
    detect_gaps,
    drop_out_of_order,
    validate_candle_ohlc,
)


@dataclass(slots=True)
class SyncResult:
    instrument_symbol: str
    timeframe: str
    upserted: int
    gaps_detected: int
    dropped_out_of_order: int
    quality_flag_counts: dict[str, int]


async def upsert_candles(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    provider_id: uuid.UUID,
    timeframe: str,
    candles: list[NormalizedCandle],
) -> SyncResult:
    ordered, dropped = drop_out_of_order(candles)
    flag_counts: dict[str, int] = {}
    rows: list[dict] = []
    now = datetime.now(UTC)

    for candle in ordered:
        flags = validate_candle_ohlc(candle)
        for flag in flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
        rows.append(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "open_time": candle.open_time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "provider_id": provider_id,
                "is_final": candle.is_final,
                "quality_flags": flags,
                "received_at": now,
            }
        )

    upserted = 0
    if rows:
        stmt = insert(Candle).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candle_identity",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "is_final": stmt.excluded.is_final,
                "quality_flags": stmt.excluded.quality_flags,
                "received_at": stmt.excluded.received_at,
            },
        )
        await session.execute(stmt)
        upserted = len(rows)

    gaps = detect_gaps(ordered, timeframe=timeframe)
    for gap_start, gap_end in gaps:
        existing = await session.execute(
            select(MarketDataGap).where(
                MarketDataGap.instrument_id == instrument_id,
                MarketDataGap.timeframe == timeframe,
                MarketDataGap.gap_start == gap_start,
                MarketDataGap.gap_end == gap_end,
                MarketDataGap.status == "open",
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                MarketDataGap(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    gap_start=gap_start,
                    gap_end=gap_end,
                    status="open",
                    details={"source": "ingest_detect"},
                )
            )

    return SyncResult(
        instrument_symbol="",
        timeframe=timeframe,
        upserted=upserted,
        gaps_detected=len(gaps),
        dropped_out_of_order=dropped,
        quality_flag_counts=flag_counts,
    )


async def sync_instrument_candles(
    session: AsyncSession,
    provider: MarketDataProvider,
    *,
    canonical_symbol: str,
    timeframe: str,
    limit: int = 200,
) -> SyncResult:
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise AppError(
            "UNSUPPORTED_TIMEFRAME",
            f"Unsupported timeframe {timeframe!r}",
            retryable=False,
        )

    await ensure_binance_catalog(session)
    instrument = await get_instrument_by_symbol(session, canonical_symbol)
    if instrument is None or not instrument.enabled:
        raise AppError("INSTRUMENT_NOT_FOUND", f"Unknown instrument {canonical_symbol}", retryable=False)

    mapping = await get_provider_mapping(session, instrument_id=instrument.id, provider_code=provider.code)
    if mapping is None:
        raise AppError(
            "PROVIDER_MAPPING_MISSING",
            f"No mapping for {canonical_symbol} on {provider.code}",
            retryable=False,
        )
    market_provider, provider_symbol = mapping

    candles = await provider.fetch_candles(
        provider_symbol=provider_symbol.provider_symbol,
        timeframe=timeframe,
        limit=limit,
    )
    result = await upsert_candles(
        session,
        instrument_id=instrument.id,
        provider_id=market_provider.id,
        timeframe=timeframe,
        candles=candles,
    )
    result.instrument_symbol = canonical_symbol
    await session.commit()
    return result
