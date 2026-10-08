"""Replay wyckoff-hdm on stored candles (no live fetch). Measured numbers only."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal

from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.replay import run_replay
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_features.types import CandleBar
from sqlalchemy import select

CRYPTO_DAILY = (
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "LTC/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "DOT/USDT",
    "ATOM/USDT",
    "NEAR/USDT",
    "UNI/USDT",
    "TRX/USDT",
    "FIL/USDT",
)
CRYPTO_4H = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")
FX_1H = ("EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD")
DIRECTIONS = ("long", "short")


async def load_bars(
    session,
    symbol: str,
    timeframe: str,
    *,
    since: datetime | None = None,
) -> list[CandleBar]:
    instrument = (
        await session.execute(select(Instrument).where(Instrument.canonical_symbol == symbol))
    ).scalar_one_or_none()
    if instrument is None:
        return []
    q = select(Candle).where(
        Candle.instrument_id == instrument.id,
        Candle.timeframe == timeframe,
        Candle.is_final.is_(True),
    )
    if since is not None:
        q = q.where(Candle.open_time >= since)
    rows = (await session.execute(q.order_by(Candle.open_time.asc()))).scalars().all()
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


def replay(bars: list[CandleBar], *, symbol: str, timeframe: str, direction: str):
    fp = dataset_fingerprint(bars, symbol=symbol, timeframe=timeframe)
    return run_replay(
        bars,
        symbol=symbol,
        timeframe=timeframe,
        dataset_fingerprint=fp,
        config={"direction": direction, "max_bars_in_trade": 20, "qty": "1"},
    )


def print_row(symbol: str, timeframe: str, direction: str, bars: list[CandleBar], report) -> dict:
    m = report.metrics
    wr = None if m.win_rate is None else round(m.win_rate * 100, 1)
    exp = None if m.expectancy_r is None else round(float(m.expectancy_r), 3)
    first = bars[0].open_time.isoformat() if bars else None
    last = bars[-1].open_time.isoformat() if bars else None
    print(
        f"{symbol:10} {timeframe:3} {direction:5}  bars={len(bars):6}  "
        f"{first} .. {last}  "
        f"n={m.trade_count:4}  W={m.win_count:3} L={m.loss_count:3}  "
        f"WR={wr}%  mean_R={exp}  pnl={m.total_pnl}  "
        f"exits={(m.slices or {}).get('exit_reason', {})}",
        flush=True,
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "bars": len(bars),
        "trades": m.trade_count,
        "wins": m.win_count,
        "losses": m.loss_count,
        "expectancy_r": m.expectancy_r,
        "pnl_r_sum": float(sum((t.pnl_r for t in report.trades), Decimal("0"))),
    }


def print_bucket(title: str, rows: list[dict]) -> None:
    trades = sum(r["trades"] for r in rows)
    wins = sum(r["wins"] for r in rows)
    r_sum = sum(r["pnl_r_sum"] for r in rows)
    print(f"\n=== {title} ===", flush=True)
    if not trades:
        print("no trades (gates found no ENTER)", flush=True)
        return
    print(
        f"trades={trades}  win_rate={round(100 * wins / trades, 1)}%  "
        f"mean_R={r_sum / trades:.3f}",
        flush=True,
    )


async def run_jobs(session, jobs: list[tuple[str, str]]) -> list[dict]:
    rows: list[dict] = []
    cache: dict[tuple[str, str], list[CandleBar]] = {}
    for symbol, timeframe in jobs:
        key = (symbol, timeframe)
        if key not in cache:
            bars = await load_bars(session, symbol, timeframe)
            cache[key] = bars
            print(f"loaded {symbol} {timeframe} n={len(bars)}", flush=True)
        bars = cache[key]
        if len(bars) < 80:
            print(f"skip {symbol} {timeframe}: bars={len(bars)}", flush=True)
            continue
        for direction in DIRECTIONS:
            report = replay(bars, symbol=symbol, timeframe=timeframe, direction=direction)
            rows.append(print_row(symbol, timeframe, direction, bars, report))
    return rows


async def main() -> None:
    factory = get_session_factory()
    print(
        "engine=wyckoff-hdm-v1  fill=next_open  ambiguity=conservative  "
        "min_rr=2.0  max_bars=20  qty=1  costs=fee10+slip5+spread2 bps",
        flush=True,
    )
    async with factory() as session:
        daily_jobs = [(s, "1d") for s in CRYPTO_DAILY]
        h4_jobs = [(s, "4h") for s in CRYPTO_4H]
        fx_jobs = [(s, "1h") for s in FX_1H]
        daily = await run_jobs(session, daily_jobs)
        print_bucket("crypto 1d listing-max, long+short", daily)
        h4 = await run_jobs(session, h4_jobs)
        print_bucket("crypto 4h BTC/ETH/BNB/SOL listing-max, long+short", h4)
        fx = await run_jobs(session, fx_jobs)
        print_bucket("forex 1h ~2y Yahoo, long+short (volume often 0)", fx)
        print_bucket("all buckets combined", daily + h4 + fx)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
