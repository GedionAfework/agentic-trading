"""Walk-forward research: completed 4h trend, 1h BOS/volume entries."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product

from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from sqlalchemy import select

from _oos_strategy_search import (
    Config,
    Metrics,
    Series,
    adverse_entry,
    adverse_exit,
    ema,
    prior_swings,
    volume_ratio,
)

SYMBOLS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")
TEST_START = datetime(2024, 1, 1, tzinfo=UTC)


@dataclass(slots=True)
class MtfSeries:
    entry: Series
    htf_index: list[int | None]
    htf_closes: list[float]
    htf_ema12: list[float | None]
    htf_ema21: list[float | None]
    htf_ema50: list[float | None]


def htf_passes(series: MtfSeries, i: int, mode: str) -> bool:
    j = series.htf_index[i]
    if j is None:
        return False
    close = series.htf_closes[j]
    e12 = series.htf_ema12[j]
    e21 = series.htf_ema21[j]
    e50 = series.htf_ema50[j]
    if e50 is None:
        return False
    if mode == "close50":
        return close > e50
    if mode == "stack":
        return e12 is not None and e21 is not None and close > e12 > e21 > e50
    prior = series.htf_ema50[j - 10] if j >= 10 else None
    if mode == "close50_slope":
        return prior is not None and close > e50 > prior
    if mode == "stack_slope":
        return (
            prior is not None
            and e12 is not None
            and e21 is not None
            and close > e12 > e21 > e50 > prior
        )
    raise ValueError(mode)


def simulate(series: MtfSeries, cfg: Config, *, test: bool) -> Metrics:
    bars = series.entry
    metrics = Metrics()
    seen: set[tuple[int, float]] = set()
    open_trade: dict[str, float | int] | None = None
    pending: dict[str, float | int] | None = None

    for i, time in enumerate(bars.times):
        is_test = time >= TEST_START
        in_period = is_test == test

        # Never let a training trade consume post-cutoff outcomes.
        if not in_period and open_trade is not None:
            open_trade = None
        if not in_period and pending is not None:
            pending = None

        if open_trade is not None:
            stop = float(open_trade["stop"])
            target = float(open_trade["target"])
            hit_stop = bars.lows[i] <= stop
            hit_target = bars.highs[i] >= target
            exit_raw: float | None = None
            if hit_stop:  # conservative if stop and target share a candle
                exit_raw = stop
            elif hit_target:
                exit_raw = target
            elif i - int(open_trade["entry_i"]) >= cfg.max_bars:
                exit_raw = bars.closes[i]
            if exit_raw is not None:
                entry = float(open_trade["entry"])
                risk = entry - stop
                exit_fill = adverse_exit(exit_raw)
                cogs = entry * 0.001 + exit_fill * 0.001
                pnl_r = (exit_fill - entry - cogs) / risk if risk > 0 else 0.0
                metrics.add(pnl_r)
                open_trade = None

        if pending is not None and open_trade is None and i == int(pending["entry_i"]):
            open_trade = {**pending, "entry": adverse_entry(bars.opens[i])}
            pending = None

        if (
            not in_period
            or open_trade is not None
            or pending is not None
            or i >= len(bars.times) - 1
        ):
            continue
        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        vr = bars.vol_ratio[i]
        if swing_hi is None or swing_lo is None or vr is None:
            continue
        if swing_hi in seen:
            continue
        if bars.closes[i] <= swing_hi[1] or vr < cfg.vol_threshold:
            continue
        if not htf_passes(series, i, cfg.trend):
            continue
        stop = swing_lo[1]
        signal_close = bars.closes[i]
        risk = signal_close - stop
        if risk <= 0:
            continue
        seen.add(swing_hi)
        pending = {
            "entry_i": i + 1,
            "stop": stop,
            "target": signal_close + risk * cfg.rr,
        }
    return metrics


async def candle_rows(session, instrument_id, timeframe: str):
    return (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == instrument_id,
                Candle.timeframe == timeframe,
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time)
        )
    ).scalars().all()


async def load_series(session, symbol: str) -> MtfSeries:
    instrument = (
        await session.execute(select(Instrument).where(Instrument.canonical_symbol == symbol))
    ).scalar_one()
    one_rows = await candle_rows(session, instrument.id, "1h")
    four_rows = await candle_rows(session, instrument.id, "4h")

    times = [r.open_time for r in one_rows]
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

    four_times = [r.open_time for r in four_rows]
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


def aggregate(series: list[MtfSeries], cfg: Config, *, test: bool) -> Metrics:
    total = Metrics()
    for item in series:
        result = simulate(item, cfg, test=test)
        total.trades += result.trades
        total.wins += result.wins
        total.r_sum += result.r_sum
    return total


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series = [await load_series(session, symbol) for symbol in SYMBOLS]
    print(
        "Loaded "
        + ", ".join(
            f"{s.entry.symbol}=1h:{len(s.entry.times)}/4h:{len(s.htf_closes)}" for s in series
        ),
        flush=True,
    )

    configs = [
        Config(*values)
        for values in product(
            ("close50", "stack", "close50_slope", "stack_slope"),
            (1.2, 1.5, 1.8, 2.0),
            (1.5, 2.0, 2.5, 3.0),
            (20, 40, 80),
        )
    ]
    ranked: list[tuple[float, Config, Metrics]] = []
    for cfg in configs:
        train = aggregate(series, cfg, test=False)
        if train.trades < 100:
            continue
        score = train.mean_r - 1.0 / (train.trades**0.5)
        ranked.append((score, cfg, train))
    ranked.sort(key=lambda row: row[0], reverse=True)

    print("\nTop five selected only on pre-2024 data:", flush=True)
    for _score, cfg, train in ranked[:5]:
        print(
            f"{cfg} train n={train.trades} WR={train.win_rate:.1%} mean_R={train.mean_r:.3f}",
            flush=True,
        )

    winner = ranked[0][1]
    baseline = Config("close50", 1.5, 2.0, 40)
    print("\nUntouched 2024+ test:", flush=True)
    for label, cfg in (("baseline_4h", baseline), ("winner_4h", winner)):
        result = aggregate(series, cfg, test=True)
        print(
            f"{label} {cfg} test n={result.trades} "
            f"WR={result.win_rate:.1%} mean_R={result.mean_r:.3f}",
            flush=True,
        )
        for item in series:
            one = simulate(item, cfg, test=True)
            print(
                f"  {item.entry.symbol} n={one.trades} "
                f"WR={one.win_rate:.1%} mean_R={one.mean_r:.3f}",
                flush=True,
            )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
