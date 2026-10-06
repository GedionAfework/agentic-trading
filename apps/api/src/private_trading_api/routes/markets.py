from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import NotFoundError
from private_trading_db.models.market import Candle
from private_trading_db.services.audit import record_audit
from private_trading_market_data.catalog import (
    ensure_binance_catalog,
    get_instrument_by_symbol,
    list_enabled_instruments,
)
from private_trading_market_data.health import market_health
from private_trading_market_data.ingest import sync_instrument_candles
from private_trading_market_data.providers import BinanceSpotProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.markets import (
    CandleOut,
    InstrumentOut,
    MarketSnapshotOut,
    ProviderHealthOut,
    SyncRequest,
    SyncResponse,
)

router = APIRouter(prefix="/markets", tags=["markets"])


def _provider(settings: Settings) -> BinanceSpotProvider:
    return BinanceSpotProvider(
        base_url=settings.binance_base_url,
        timeout_seconds=settings.market_http_timeout_seconds,
    )


@router.get("/instruments", response_model=list[InstrumentOut])
async def get_instruments(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InstrumentOut]:
    user.require_roles("owner", "admin", "viewer")
    await ensure_binance_catalog(session)
    await session.commit()
    instruments = await list_enabled_instruments(session)
    return [
        InstrumentOut(
            id=i.id,
            canonical_symbol=i.canonical_symbol,
            asset_class=i.asset_class,
            base_asset=i.base_asset,
            quote_asset=i.quote_asset,
            enabled=i.enabled,
        )
        for i in instruments
    ]


@router.get("/candles", response_model=list[CandleOut])
async def get_candles(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    symbol: Annotated[str, Query(min_length=3, max_length=64)],
    timeframe: Annotated[str, Query(min_length=2, max_length=12)] = "15m",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[CandleOut]:
    user.require_roles("owner", "admin", "viewer")
    instrument = await get_instrument_by_symbol(session, symbol)
    if instrument is None:
        raise NotFoundError(f"Instrument {symbol} not found")
    result = await session.execute(
        select(Candle)
        .where(Candle.instrument_id == instrument.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return [
        CandleOut(
            open_time=c.open_time,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            is_final=c.is_final,
            quality_flags=[str(f) for f in (c.quality_flags or [])],
        )
        for c in rows
    ]


@router.post("/sync", response_model=SyncResponse)
async def post_sync(
    body: SyncRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SyncResponse:
    user.require_roles("owner", "admin")
    provider = _provider(settings)
    try:
        result = await sync_instrument_candles(
            session,
            provider,
            canonical_symbol=body.symbol,
            timeframe=body.timeframe,
            limit=body.limit,
        )
    finally:
        await provider.aclose()

    await record_audit(
        session,
        action="market.candles_synced",
        actor_type="user",
        actor_id=user.id,
        resource_type="instrument",
        resource_id=None,
        correlation_id=get_correlation_id(request),
        metadata={
            "symbol": result.instrument_symbol,
            "timeframe": result.timeframe,
            "upserted": result.upserted,
            "gaps_detected": result.gaps_detected,
        },
    )
    await session.commit()
    return SyncResponse(
        instrument_symbol=result.instrument_symbol,
        timeframe=result.timeframe,
        upserted=result.upserted,
        gaps_detected=result.gaps_detected,
        dropped_out_of_order=result.dropped_out_of_order,
        quality_flag_counts=result.quality_flag_counts,
    )


@router.get("/health", response_model=list[MarketSnapshotOut])
async def get_market_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[MarketSnapshotOut]:
    user.require_roles("owner", "admin", "viewer")
    await ensure_binance_catalog(session)
    await session.commit()
    tfs = tuple(
        tf.strip() for tf in settings.market_default_timeframes.split(",") if tf.strip()
    ) or ("15m", "1h")
    snapshots = await market_health(session, timeframes=tfs)
    return [
        MarketSnapshotOut(
            instrument_symbol=s.instrument_symbol,
            timeframe=s.timeframe,
            as_of=s.as_of,
            last_open_time=s.last_open_time,
            last_close=s.last_close,
            candle_count=s.candle_count,
            fresh=s.fresh,
            actionable=s.actionable,
            quality_flags=s.quality_flags,
            gaps_open=s.gaps_open,
        )
        for s in snapshots
    ]


@router.get("/provider/health", response_model=ProviderHealthOut)
async def get_provider_health(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProviderHealthOut:
    user.require_roles("owner", "admin", "viewer")
    provider = _provider(settings)
    try:
        health = await provider.health()
    finally:
        await provider.aclose()
    return ProviderHealthOut(
        provider_code=health.provider_code,
        ok=health.ok,
        latency_ms=health.latency_ms,
        message=health.message,
        degraded=health.degraded,
    )
