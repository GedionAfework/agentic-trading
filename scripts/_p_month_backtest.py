"""Replay ~1 month of real Binance 1h candles through the deterministic engine.

Not a guess — same strategy/risk/fill path as production paper simulation.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.replay import run_replay
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_features.types import CandleBar
from private_trading_market_data.catalog import ensure_binance_catalog
from private_trading_market_data.ingest import sync_instrument_candles
from private_trading_market_data.providers import BinanceSpotProvider
from private_trading_core.config import get_settings
from sqlalchemy import select


SYMBOLS = ("BTC/USDT", "ETH/USDT")
TIMEFRAME = "1h"
LIMIT = 720  # ~30 days of 1h bars


async def sync_and_load(session, provider, symbol: str) -> list[CandleBar]:
    await sync_instrument_candles(
        session,
        provider,
        canonical_symbol=symbol,
        timeframe=TIMEFRAME,
        limit=LIMIT,
    )
    await session.commit()
    instrument = (
        await session.execute(select(Instrument).where(Instrument.canonical_symbol == symbol))
    ).scalar_one()
    cutoff = datetime.now(UTC) - timedelta(days=31)
    rows = (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == instrument.id,
                Candle.timeframe == TIMEFRAME,
                Candle.is_final.is_(True),
                Candle.open_time >= cutoff,
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


def summarize(report) -> dict:
    m = report.metrics
    trades = report.trades
    return {
        "bars": report.bar_count if hasattr(report, "bar_count") else None,
        "trade_count": m.trade_count,
        "wins": m.win_count,
        "losses": m.loss_count,
        "win_rate": None if m.win_rate is None else round(m.win_rate * 100, 1),
        "expectancy_r": None if m.expectancy_r is None else round(float(m.expectancy_r), 3),
        "total_pnl": str(m.total_pnl),
        "max_dd_pnl": str(m.max_drawdown_pnl),
        "exit_reasons": (m.slices or {}).get("exit_reason", {}),
        "trades": [
            {
                "dir": t.direction,
                "entry": str(t.entry_price),
                "exit": str(t.exit_price),
                "pnl_r": float(t.pnl_r),
                "reason": t.exit_reason,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            }
            for t in trades
        ],
    }


async def main() -> None:
    settings = get_settings()
    provider = BinanceSpotProvider(
        base_url=settings.binance_base_url,
        timeout_seconds=settings.market_http_timeout_seconds,
    )
    factory = get_session_factory()
    try:
        async with factory() as session:
            await ensure_binance_catalog(session)
            await session.commit()
            print("=== ~1 month replay (deterministic wyckoff-hdm, next_open, conservative) ===")
            print(f"window~31d  timeframe={TIMEFRAME}  qty=1  equity=10000  costs=fee10+slip5+spread2 bps")
            combined_r = Decimal("0")
            combined_trades = 0
            combined_wins = 0
            for symbol in SYMBOLS:
                bars = await sync_and_load(session, provider, symbol)
                if len(bars) < 50:
                    print(f"\n{symbol}: only {len(bars)} bars — skip")
                    continue
                fp = dataset_fingerprint(bars, symbol=symbol, timeframe=TIMEFRAME)
                report = run_replay(
                    bars,
                    symbol=symbol,
                    timeframe=TIMEFRAME,
                    dataset_fingerprint=fp,
                    config={"direction": "long", "max_bars_in_trade": 20, "qty": "1"},
                )
                s = summarize(report)
                print(f"\n--- {symbol} ---")
                print(
                    f"bars={len(bars)}  first={bars[0].open_time.isoformat()}  "
                    f"last={bars[-1].open_time.isoformat()}"
                )
                print(
                    f"trades={s['trade_count']}  wins={s['wins']}  losses={s['losses']}  "
                    f"win_rate={s['win_rate']}%  expectancy_R={s['expectancy_r']}  "
                    f"total_pnl={s['total_pnl']}  max_dd={s['max_dd_pnl']}"
                )
                print(f"exits={s['exit_reasons']}")
                for t in s["trades"][:20]:
                    print(
                        f"  {t['entry_time']} → {t['exit_time']}  "
                        f"R={t['pnl_r']:+.3f}  {t['reason']}  "
                        f"entry={t['entry']} exit={t['exit']}"
                    )
                if len(s["trades"]) > 20:
                    print(f"  … {len(s['trades']) - 20} more")
                combined_trades += s["trade_count"]
                combined_wins += s["wins"]
                if s["expectancy_r"] is not None and s["trade_count"]:
                    combined_r += Decimal(str(s["expectancy_r"])) * Decimal(s["trade_count"])
            print("\n=== aggregate ===")
            if combined_trades:
                print(
                    f"trades={combined_trades}  win_rate={round(100 * combined_wins / combined_trades, 1)}%  "
                    f"mean_R={float(combined_r / Decimal(combined_trades)):.3f}"
                )
            else:
                print("No trades fired in this window (prefilter/strategy gates found no ENTER setups).")
            print(
                "\nNote: this is historical replay of the coded rules — not a live P&L guarantee, "
                "and not ML guessing."
            )
    finally:
        await provider.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
