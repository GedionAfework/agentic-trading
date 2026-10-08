"""Seed an ENTER decision + synthetic closed candles for paper smoke (dev only)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_db.models.decision_record import DecisionRecord
from private_trading_db.models.identity import User
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_market_data.catalog import ensure_binance_catalog
from sqlalchemy import delete, select


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        provider = await ensure_binance_catalog(session)
        await session.commit()
        owner = (
            await session.execute(select(User).where(User.email == "owner@example.com"))
        ).scalar_one()
        instrument = (
            await session.execute(
                select(Instrument).where(Instrument.canonical_symbol == "BTC/USDT")
            )
        ).scalar_one()
        base = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
        await session.execute(
            delete(Candle).where(
                Candle.instrument_id == instrument.id,
                Candle.timeframe == "1h",
                Candle.open_time >= base,
                Candle.open_time < base + timedelta(hours=10),
            )
        )
        rows = [
            (0, "120", "125", "118", "124"),
            (1, "124", "126", "122", "125"),
            (2, "125", "128", "123", "127"),
            (3, "127", "130", "126", "129"),
            (4, "129", "140", "128", "139"),
        ]
        for i, o, h, low, c in rows:
            session.add(
                Candle(
                    instrument_id=instrument.id,
                    timeframe="1h",
                    open_time=base + timedelta(hours=i),
                    open=Decimal(o),
                    high=Decimal(h),
                    low=Decimal(low),
                    close=Decimal(c),
                    volume=Decimal("100"),
                    provider_id=provider.id,
                    is_final=True,
                    quality_flags=[],
                )
            )
        record = DecisionRecord(
            owner_user_id=owner.id,
            symbol="BTC/USDT",
            timeframe="1h",
            bar_open_time=base,
            action="ENTER",
            direction="long",
            setup_state="ready_for_review",
            confidence_band="medium",
            strategy_code="wyckoff-hdm",
            strategy_version_no=1,
            risk_approved=True,
            entry_price=124.0,
            stop_price=116.0,
            target_price=138.0,
            rr_ratio=1.75,
            explanation="PAPER smoke ENTER from seeded decision.",
            explanation_source="deterministic_template",
            evidence={"invalidation_price": "115"},
            workflow=[{"agent": "smoke", "status": "ok"}],
            hard_blockers=[],
        )
        session.add(record)
        await session.commit()
        print(f"decision_id={record.id}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
