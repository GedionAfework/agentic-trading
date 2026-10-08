"""Long-only BOS+volume with EMA50 HTF on stored daily majors."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.replay import run_replay
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_features.types import CandleBar
from sqlalchemy import select

SYMS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")


async def load(session, symbol: str, timeframe: str) -> list[CandleBar]:
    inst = (
        await session.execute(select(Instrument).where(Instrument.canonical_symbol == symbol))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == inst.id,
                Candle.timeframe == timeframe,
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time.asc())
        )
    ).scalars().all()
    return [
        CandleBar(
            open_time=r.open_time,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
            is_final=True,
        )
        for r in rows
    ]


async def main() -> None:
    factory = get_session_factory()
    trades = wins = 0
    rsum = 0.0
    async with factory() as session:
        for symbol in SYMS:
            bars = await load(session, symbol, "1d")
            fp = dataset_fingerprint(bars, symbol=symbol, timeframe="1d")
            rep = run_replay(
                bars,
                symbol=symbol,
                timeframe="1d",
                dataset_fingerprint=fp,
                config={"direction": "long", "qty": "1"},
            )
            m = rep.metrics
            wr = None if m.win_rate is None else round(m.win_rate * 100, 1)
            exp = None if m.expectancy_r is None else round(float(m.expectancy_r), 3)
            print(
                f"{symbol} 1d long n={m.trade_count} W={m.win_count} L={m.loss_count} "
                f"WR={wr}% mean_R={exp} exits={(m.slices or {}).get('exit_reason', {})}",
                flush=True,
            )
            trades += m.trade_count
            wins += m.win_count
            rsum += float(sum((t.pnl_r for t in rep.trades), Decimal("0")))
    print("=== majors 1d long hybrid ===", flush=True)
    if trades:
        print(
            f"trades={trades} win_rate={round(100 * wins / trades, 1)}% mean_R={rsum / trades:.3f}",
            flush=True,
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
