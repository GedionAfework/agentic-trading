from __future__ import annotations

import uuid
from decimal import Decimal

from private_trading_db.models.market import Instrument, MarketProvider, ProviderSymbol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_market_data.providers.binance import DEFAULT_SYMBOLS
from private_trading_market_data.providers.yahoo_fx import DEFAULT_FX_SYMBOLS

BINANCE_PROVIDER_CODE = "binance_spot"
BINANCE_BASE_URL = "https://api.binance.com"
YAHOO_FX_PROVIDER_CODE = "yahoo_fx"
YAHOO_FX_BASE_URL = "https://query1.finance.yahoo.com"

DEFAULT_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


async def ensure_binance_catalog(session: AsyncSession) -> MarketProvider:
    result = await session.execute(
        select(MarketProvider).where(MarketProvider.code == BINANCE_PROVIDER_CODE)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        provider = MarketProvider(
            code=BINANCE_PROVIDER_CODE,
            name="Binance Spot",
            base_url=BINANCE_BASE_URL,
            status="active",
            config={"public_rest": True},
        )
        session.add(provider)
        await session.flush()

    for info in DEFAULT_SYMBOLS:
        inst_result = await session.execute(
            select(Instrument).where(Instrument.canonical_symbol == info.canonical_symbol)
        )
        instrument = inst_result.scalar_one_or_none()
        if instrument is None:
            instrument = Instrument(
                canonical_symbol=info.canonical_symbol,
                asset_class=info.asset_class,
                base_asset=info.base_asset,
                quote_asset=info.quote_asset,
                price_tick=info.price_tick or Decimal("0.01"),
                qty_step=info.qty_step or Decimal("0.0001"),
                enabled=True,
            )
            session.add(instrument)
            await session.flush()

        map_result = await session.execute(
            select(ProviderSymbol).where(
                ProviderSymbol.provider_id == provider.id,
                ProviderSymbol.instrument_id == instrument.id,
            )
        )
        mapping = map_result.scalar_one_or_none()
        if mapping is None:
            session.add(
                ProviderSymbol(
                    provider_id=provider.id,
                    instrument_id=instrument.id,
                    provider_symbol=info.provider_symbol,
                    interval_map=DEFAULT_INTERVAL_MAP,
                    enabled=True,
                )
            )

    await session.flush()
    return provider


async def ensure_forex_catalog(session: AsyncSession) -> MarketProvider:
    """Register major FX pairs from the free Yahoo chart provider."""
    result = await session.execute(
        select(MarketProvider).where(MarketProvider.code == YAHOO_FX_PROVIDER_CODE)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        provider = MarketProvider(
            code=YAHOO_FX_PROVIDER_CODE,
            name="Yahoo Finance FX",
            base_url=YAHOO_FX_BASE_URL,
            status="active",
            config={
                "public_rest": True,
                "notes": [
                    "Free research OHLC; volume often zero.",
                    "Not a licensed FX prime broker feed.",
                ],
            },
        )
        session.add(provider)
        await session.flush()

    fx_interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "60m",
        "4h": "60m",
        "1d": "1d",
    }
    for info in DEFAULT_FX_SYMBOLS:
        inst_result = await session.execute(
            select(Instrument).where(Instrument.canonical_symbol == info.canonical_symbol)
        )
        instrument = inst_result.scalar_one_or_none()
        if instrument is None:
            instrument = Instrument(
                canonical_symbol=info.canonical_symbol,
                asset_class=info.asset_class,
                base_asset=info.base_asset,
                quote_asset=info.quote_asset,
                price_tick=info.price_tick or Decimal("0.00001"),
                qty_step=info.qty_step or Decimal("0.01"),
                enabled=True,
            )
            session.add(instrument)
            await session.flush()

        map_result = await session.execute(
            select(ProviderSymbol).where(
                ProviderSymbol.provider_id == provider.id,
                ProviderSymbol.instrument_id == instrument.id,
            )
        )
        mapping = map_result.scalar_one_or_none()
        if mapping is None:
            session.add(
                ProviderSymbol(
                    provider_id=provider.id,
                    instrument_id=instrument.id,
                    provider_symbol=info.provider_symbol,
                    interval_map=fx_interval_map,
                    enabled=True,
                )
            )

    await session.flush()
    return provider


async def list_enabled_instruments(session: AsyncSession) -> list[Instrument]:
    result = await session.execute(
        select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.canonical_symbol)
    )
    return list(result.scalars().all())


async def get_instrument_by_symbol(
    session: AsyncSession, canonical_symbol: str
) -> Instrument | None:
    result = await session.execute(
        select(Instrument).where(Instrument.canonical_symbol == canonical_symbol)
    )
    return result.scalar_one_or_none()


async def get_provider_mapping(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    provider_code: str = BINANCE_PROVIDER_CODE,
) -> tuple[MarketProvider, ProviderSymbol] | None:
    result = await session.execute(
        select(MarketProvider, ProviderSymbol)
        .join(ProviderSymbol, ProviderSymbol.provider_id == MarketProvider.id)
        .where(MarketProvider.code == provider_code)
        .where(ProviderSymbol.instrument_id == instrument_id)
        .where(ProviderSymbol.enabled.is_(True))
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]
