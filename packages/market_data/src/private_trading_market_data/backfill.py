"""Historical candle backfill from free public providers."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.market import Candle
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_market_data.catalog import (
    ensure_binance_catalog,
    ensure_forex_catalog,
    get_instrument_by_symbol,
    get_provider_mapping,
)
from private_trading_market_data.ingest import upsert_candles
from private_trading_market_data.providers.binance import DEFAULT_SYMBOLS, BinanceSpotProvider
from private_trading_market_data.providers.yahoo_fx import DEFAULT_FX_SYMBOLS, YahooFxProvider


@dataclass(slots=True)
class BackfillResult:
    provider: str
    instrument_symbol: str
    timeframe: str
    upserted: int
    pages: int
    earliest: str | None
    latest: str | None
    error: str | None = None


async def _earliest_stored(
    session: AsyncSession, *, instrument_id, timeframe: str
) -> datetime | None:
    result = await session.execute(
        select(func.min(Candle.open_time)).where(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
        )
    )
    return result.scalar_one_or_none()


async def _latest_stored(
    session: AsyncSession, *, instrument_id, timeframe: str
) -> datetime | None:
    result = await session.execute(
        select(func.max(Candle.open_time)).where(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
        )
    )
    return result.scalar_one_or_none()


async def backfill_binance_symbol(
    session: AsyncSession,
    provider: BinanceSpotProvider,
    *,
    canonical_symbol: str,
    timeframe: str,
    page_pause_seconds: float = 0.25,
    max_pages: int = 10_000,
) -> BackfillResult:
    """Walk Binance klines from the earliest available bar to now (1000/page)."""
    await ensure_binance_catalog(session)
    await session.commit()
    instrument = await get_instrument_by_symbol(session, canonical_symbol)
    if instrument is None:
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error="instrument_not_found",
        )
    mapping = await get_provider_mapping(
        session, instrument_id=instrument.id, provider_code=provider.code
    )
    if mapping is None:
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error="mapping_missing",
        )
    market_provider, provider_symbol = mapping

    listing_anchor = datetime(2018, 1, 1, tzinfo=UTC)
    stored_first = await _earliest_stored(
        session, instrument_id=instrument.id, timeframe=timeframe
    )
    stored_last = await _latest_stored(session, instrument_id=instrument.id, timeframe=timeframe)
    # If we already hold history from near listing, only extend the tip (fast re-runs).
    # If the tip-only sync left a short recent window, walk from 2010 instead.
    if stored_first is not None and stored_first <= listing_anchor and stored_last is not None:
        cursor_start = stored_last + timedelta(milliseconds=1)
    else:
        cursor_start = datetime(2010, 1, 1, tzinfo=UTC)

    total = 0
    pages = 0
    while pages < max_pages:
        batch: list = []
        last_error: str | None = None
        for attempt in range(1, 6):
            try:
                batch = await provider.fetch_candles(
                    provider_symbol=provider_symbol.provider_symbol,
                    timeframe=timeframe,
                    start=cursor_start,
                    limit=1000,
                )
                last_error = None
                break
            except AppError as exc:
                last_error = exc.message
                if not exc.retryable and attempt >= 2:
                    break
                await asyncio.sleep(min(30.0, 2.0**attempt))
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                await asyncio.sleep(min(30.0, 2.0**attempt))
        if last_error and not batch:
            return BackfillResult(
                provider=provider.code,
                instrument_symbol=canonical_symbol,
                timeframe=timeframe,
                upserted=total,
                pages=pages,
                earliest=None if stored_first is None else stored_first.isoformat(),
                latest=None if stored_last is None else stored_last.isoformat(),
                error=last_error,
            )
        if not batch:
            break
        pages += 1
        result = await upsert_candles(
            session,
            instrument_id=instrument.id,
            provider_id=market_provider.id,
            timeframe=timeframe,
            candles=batch,
        )
        await session.commit()
        total += result.upserted
        if len(batch) < 1000:
            break
        cursor_start = batch[-1].open_time + timedelta(milliseconds=1)
        await asyncio.sleep(page_pause_seconds)

    stored_first = await _earliest_stored(
        session, instrument_id=instrument.id, timeframe=timeframe
    )
    stored_last = await _latest_stored(session, instrument_id=instrument.id, timeframe=timeframe)
    return BackfillResult(
        provider=provider.code,
        instrument_symbol=canonical_symbol,
        timeframe=timeframe,
        upserted=total,
        pages=pages,
        earliest=None if stored_first is None else stored_first.isoformat(),
        latest=None if stored_last is None else stored_last.isoformat(),
    )


async def backfill_yahoo_fx_symbol(
    session: AsyncSession,
    provider: YahooFxProvider,
    *,
    canonical_symbol: str,
    timeframe: str,
) -> BackfillResult:
    """Pull Yahoo's maximum available history for one FX pair/TF in one request."""
    await ensure_forex_catalog(session)
    await session.commit()
    instrument = await get_instrument_by_symbol(session, canonical_symbol)
    if instrument is None:
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error="instrument_not_found",
        )
    mapping = await get_provider_mapping(
        session, instrument_id=instrument.id, provider_code=provider.code
    )
    if mapping is None:
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error="mapping_missing",
        )
    market_provider, provider_symbol = mapping
    try:
        candles = await provider.fetch_candles(
            provider_symbol=provider_symbol.provider_symbol,
            timeframe=timeframe,
            start=datetime(1970, 1, 1, tzinfo=UTC),
            end=datetime.now(UTC),
            limit=0,  # keep full series
        )
    except Exception as exc:  # noqa: BLE001 — surface in result row
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error=str(exc),
        )
    if not candles:
        return BackfillResult(
            provider=provider.code,
            instrument_symbol=canonical_symbol,
            timeframe=timeframe,
            upserted=0,
            pages=0,
            earliest=None,
            latest=None,
            error="empty",
        )
    # Chunk upserts to avoid huge statements
    total = 0
    chunk = 2000
    for i in range(0, len(candles), chunk):
        part = candles[i : i + chunk]
        result = await upsert_candles(
            session,
            instrument_id=instrument.id,
            provider_id=market_provider.id,
            timeframe=timeframe,
            candles=part,
        )
        await session.commit()
        total += result.upserted
    return BackfillResult(
        provider=provider.code,
        instrument_symbol=canonical_symbol,
        timeframe=timeframe,
        upserted=total,
        pages=1,
        earliest=candles[0].open_time.isoformat(),
        latest=candles[-1].open_time.isoformat(),
    )


async def run_max_free_backfill(
    session: AsyncSession,
    *,
    crypto_timeframes: tuple[str, ...] = ("15m", "1h", "4h", "1d"),
    forex_timeframes: tuple[str, ...] = ("1h", "1d"),
    crypto_symbols: tuple[str, ...] | None = None,
    forex_symbols: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    crypto_syms = (
        tuple(s.canonical_symbol for s in DEFAULT_SYMBOLS)
        if crypto_symbols is None
        else crypto_symbols
    )
    forex_syms = (
        tuple(s.canonical_symbol for s in DEFAULT_FX_SYMBOLS)
        if forex_symbols is None
        else forex_symbols
    )
    out: list[dict[str, Any]] = []

    binance = BinanceSpotProvider(timeout_seconds=60.0)
    yahoo = YahooFxProvider(timeout_seconds=90.0)
    try:
        for symbol in crypto_syms:
            for tf in crypto_timeframes:
                print(f"backfill crypto {symbol} {tf}…", flush=True)
                try:
                    result = await backfill_binance_symbol(
                        session, binance, canonical_symbol=symbol, timeframe=tf
                    )
                except Exception as exc:  # noqa: BLE001 — keep other series moving
                    result = BackfillResult(
                        provider=binance.code,
                        instrument_symbol=symbol,
                        timeframe=tf,
                        upserted=0,
                        pages=0,
                        earliest=None,
                        latest=None,
                        error=str(exc),
                    )
                print(
                    f"  -> upserted={result.upserted} pages={result.pages} "
                    f"{result.earliest} .. {result.latest} err={result.error}",
                    flush=True,
                )
                out.append(asdict(result))
        for symbol in forex_syms:
            for tf in forex_timeframes:
                print(f"backfill forex {symbol} {tf}…", flush=True)
                result = await backfill_yahoo_fx_symbol(
                    session, yahoo, canonical_symbol=symbol, timeframe=tf
                )
                print(
                    f"  -> upserted={result.upserted} pages={result.pages} "
                    f"{result.earliest} .. {result.latest} err={result.error}",
                    flush=True,
                )
                out.append(asdict(result))
    finally:
        await binance.aclose()
        await yahoo.aclose()
    return out
