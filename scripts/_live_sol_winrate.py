"""Measure SOL V1 soak-model win rate on live Binance history (no DB)."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow importing sibling research helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from private_trading_market_data.providers.binance import BinanceSpotProvider
from private_trading_strategies.multi_market import SOL_PROFIT_MODEL, SOL_WIN_RATE_MODEL

from _mtf_oos_search import MtfSeries, htf_passes
from _oos_strategy_search import (
    Metrics,
    Series,
    adverse_entry,
    adverse_exit,
    ema,
    prior_swings,
    volume_ratio,
)
from _walkforward_challenger import ChallengerConfig, atr, simulate_year


async def fetch_all(
    provider: BinanceSpotProvider,
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
) -> list:
    out = []
    cursor = start
    while True:
        batch = await provider.fetch_candles(
            provider_symbol=symbol,
            timeframe=timeframe,
            start=cursor,
            limit=1000,
        )
        if not batch:
            break
        out.extend(batch)
        last = batch[-1].open_time
        nxt = last + timedelta(hours=1 if timeframe == "1h" else 4 if timeframe == "4h" else 24)
        if len(batch) < 1000 or nxt <= cursor:
            break
        cursor = nxt
        if len(out) > 60_000:
            break
    # Deduplicate by open_time
    seen: set[datetime] = set()
    unique = []
    for c in out:
        if c.open_time in seen:
            continue
        seen.add(c.open_time)
        unique.append(c)
    return unique


def build_mtf(one_rows, four_rows, *, symbol: str) -> MtfSeries:
    times = [r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC) for r in one_rows]
    opens = [float(r.open) for r in one_rows]
    highs = [float(r.high) for r in one_rows]
    lows = [float(r.low) for r in one_rows]
    closes = [float(r.close) for r in one_rows]
    volumes = [float(r.volume or 0) for r in one_rows]
    swing_high, swing_low = prior_swings(highs, lows)
    entry = Series(
        symbol=symbol,
        times=times,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        ema12=ema(closes, 12),
        ema21=ema(closes, 21),
        ema50=ema(closes, 50),
        swing_high=swing_high,
        swing_low=swing_low,
        vol_ratio=volume_ratio(volumes),
    )
    four_times = [
        r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC) for r in four_rows
    ]
    four_closes = [float(r.close) for r in four_rows]
    mapped: list[int | None] = []
    j = -1
    for one_time in times:
        decision_time = one_time + timedelta(hours=1)
        while j + 1 < len(four_times) and four_times[j + 1] + timedelta(hours=4) <= decision_time:
            j += 1
        mapped.append(j if j >= 0 else None)
    return MtfSeries(
        entry=entry,
        htf_index=mapped,
        htf_closes=four_closes,
        htf_ema12=ema(four_closes, 12),
        htf_ema21=ema(four_closes, 21),
        htf_ema50=ema(four_closes, 50),
    )


def simulate_all(series: MtfSeries, cfg: ChallengerConfig, atr_values: list) -> Metrics:
    """Run the same yearly simulator across every calendar year present."""
    years = sorted({t.year for t in series.entry.times})
    total = Metrics()
    empty_btc: dict = {}
    for year in years:
        part = simulate_year(
            series,
            cfg,
            year=year,
            atr_values=atr_values,
            btc_regime=empty_btc,
        )
        total.trades += part.trades
        total.wins += part.wins
        total.r_sum += part.r_sum
    return total


async def main() -> None:
    # Frozen soak V1 params (profit model).
    cfg = ChallengerConfig(
        htf_trend="stack_slope",
        vol_threshold=2.0,
        rr=3.0,
        max_bars=80,
        max_extension_atr=2.0,
        btc_filter=False,
        breakeven_at_1r=False,
    )
    start = datetime(2022, 1, 1, tzinfo=UTC)
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    try:
        print("fetching SOLUSDT 1h + 4h from Binance…", flush=True)
        one = await fetch_all(provider, symbol="SOLUSDT", timeframe="1h", start=start)
        four = await fetch_all(provider, symbol="SOLUSDT", timeframe="4h", start=start)
    finally:
        await provider.aclose()

    print(
        f"bars 1h={len(one)} 4h={len(four)}  "
        f"from {one[0].open_time if one else None} to {one[-1].open_time if one else None}",
        flush=True,
    )
    if len(one) < 500 or len(four) < 100:
        print("insufficient history", flush=True)
        return

    series = build_mtf(one, four, symbol="SOL/USDT")
    atr_values = atr(series.entry.highs, series.entry.lows, series.entry.closes)
    metrics = simulate_all(series, cfg, atr_values)

    wr = 100.0 * metrics.win_rate
    print("\n=== LIVE TEST: SOL V1 soak model (agent trading path) ===", flush=True)
    print(f"model: {SOL_PROFIT_MODEL.code} v{SOL_PROFIT_MODEL.version_no}", flush=True)
    print(
        f"config: trend={cfg.htf_trend} vol>={cfg.vol_threshold} "
        f"rr={cfg.rr} max_bars={cfg.max_bars} max_ext_atr={cfg.max_extension_atr}",
        flush=True,
    )
    print(f"closed_trades: {metrics.trades}", flush=True)
    print(f"wins: {metrics.wins}  losses: {metrics.trades - metrics.wins}", flush=True)
    print(f"win_rate: {wr:.1f}%", flush=True)
    print(f"mean_R: {metrics.mean_r:.3f}", flush=True)
    print(
        f"\nRegistry validation (walk-forward reference): "
        f"WR={100 * SOL_PROFIT_MODEL.validation.win_rate:.1f}% "
        f"mean_R={SOL_PROFIT_MODEL.validation.mean_r} "
        f"n={SOL_PROFIT_MODEL.validation.trades}",
        flush=True,
    )
    print(
        f"V2 win-rate alternate (not active soak): "
        f"WR={100 * SOL_WIN_RATE_MODEL.validation.win_rate:.1f}% "
        f"n={SOL_WIN_RATE_MODEL.validation.trades}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
