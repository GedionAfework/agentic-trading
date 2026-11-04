"""Step 6 v4: SOL 1d bias + 1h entry + scale-out (beat V2 win rate?).

Hypothesis/gates: docs/strategy/STEP6_HYPOTHESIS_V4.md
Fetches Binance public candles (no DB). Does not edit V1/V2 or the registry.
"""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from private_trading_backtest.walkforward import (
    ResearchObjective,
    ResearchPerformance,
    SelectionPolicy,
    TimeFold,
    combine_performance,
    evaluate_promotion,
    pair_cost_bps,
    run_walk_forward,
)
from private_trading_market_data.providers.binance import BinanceSpotProvider

from _oos_strategy_search import Series, ema, prior_swings, volume_ratio
from _walkforward_challenger import atr

SYMBOL = "SOL/USDT"
PROVIDER_SYMBOL = "SOLUSDT"
FEE_RATE = 0.001
V2_WIN_RATE = 0.589
V2_MEAN_R = 0.059
TEST_YEARS = (2022, 2023, 2024, 2025, 2026)
CATALOG = "sol-mtf-daily1h-scaleout-v4"


@dataclass(slots=True)
class Daily1hSeries:
    entry: Series
    atr_values: list[float | None]
    htf_index: list[int | None]
    htf_closes: list[float]
    htf_ema12: list[float | None]
    htf_ema21: list[float | None]
    htf_ema50: list[float | None]


@dataclass(slots=True, frozen=True)
class Daily1hWrConfig:
    trend: str
    vol_threshold: float
    partial_r: float
    target_r: float
    max_bars: int
    max_extension_atr: float = 2.0


def _fill(raw: float, *, entering: bool) -> float:
    bps = pair_cost_bps(SYMBOL) / 10_000.0
    return raw * (1.0 + bps) if entering else raw * (1.0 - bps)


def htf_passes(series: Daily1hSeries, i: int, mode: str) -> bool:
    j = series.htf_index[i]
    if j is None:
        return False
    close = series.htf_closes[j]
    e12 = series.htf_ema12[j]
    e21 = series.htf_ema21[j]
    e50 = series.htf_ema50[j]
    if e50 is None:
        return False
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


def year_bounds(times: list[datetime], year: int) -> tuple[int, int]:
    start = bisect_left(times, datetime(year, 1, 1, tzinfo=UTC))
    end = bisect_left(times, datetime(year + 1, 1, 1, tzinfo=UTC))
    return start, end


def simulate_range(
    series: Daily1hSeries,
    cfg: Daily1hWrConfig,
    *,
    start_i: int,
    end_i: int,
) -> ResearchPerformance:
    bars = series.entry
    perf = ResearchPerformance()
    if end_i - start_i < 100:
        return perf
    seen: set[tuple[int, float]] = set()
    open_trade: dict | None = None
    pending: dict | None = None

    for i in range(start_i, end_i):
        if open_trade is not None:
            entry = float(open_trade["entry"])
            stop = float(open_trade["stop"])
            target = float(open_trade["target"])
            original_stop = float(open_trade["original_stop"])
            initial_risk = entry - original_stop
            remaining = float(open_trade["remaining"])
            realized = float(open_trade["realized_r"])

            # Scale-out: take partial when high reaches partial_r
            if (
                not bool(open_trade["partial_taken"])
                and bars.highs[i] >= entry + initial_risk * cfg.partial_r
            ):
                partial_exit = _fill(entry + initial_risk * cfg.partial_r, entering=False)
                fee = entry * FEE_RATE * 0.5 + partial_exit * FEE_RATE * 0.5
                realized += ((partial_exit - entry - fee) / initial_risk) * 0.5
                remaining = 0.5
                stop = entry  # breakeven
                open_trade["partial_taken"] = True
                open_trade["remaining"] = remaining
                open_trade["realized_r"] = realized
                open_trade["stop"] = stop

            hit_stop = bars.lows[i] <= stop
            hit_target = bars.highs[i] >= target
            exit_raw: float | None = None
            if hit_stop:
                exit_raw = stop
            elif hit_target:
                exit_raw = target
            elif i - int(open_trade["entry_i"]) >= cfg.max_bars:
                exit_raw = bars.closes[i]

            if exit_raw is not None:
                exit_fill = _fill(exit_raw, entering=False)
                fee = entry * FEE_RATE * remaining + exit_fill * FEE_RATE * remaining
                piece = ((exit_fill - entry - fee) / initial_risk) * remaining
                total_r = realized + piece
                perf.outcomes_r.append(total_r)
                open_trade = None

        if pending is not None and open_trade is None and i == int(pending["entry_i"]):
            entry = _fill(bars.opens[i], entering=True)
            open_trade = {
                **pending,
                "entry": entry,
                "original_stop": pending["stop"],
                "stop": pending["stop"],
                "partial_taken": False,
                "remaining": 1.0,
                "realized_r": 0.0,
            }
            pending = None

        if open_trade is not None or pending is not None or i >= end_i - 1:
            continue
        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        vr = bars.vol_ratio[i]
        atr_value = series.atr_values[i]
        if swing_hi is None or swing_lo is None or vr is None or not atr_value:
            continue
        if swing_hi in seen:
            continue
        close = bars.closes[i]
        if close <= swing_hi[1] or vr < cfg.vol_threshold:
            continue
        if not htf_passes(series, i, cfg.trend):
            continue
        extension = (close - swing_hi[1]) / atr_value
        if extension > cfg.max_extension_atr:
            continue
        stop = swing_lo[1]
        risk = close - stop
        if risk <= 0:
            continue
        seen.add(swing_hi)
        pending = {
            "entry_i": i + 1,
            "stop": stop,
            "target": close + risk * cfg.target_r,
        }
    return perf


def build_series(one_rows, daily_rows) -> Daily1hSeries:
    times = [
        r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC)
        for r in one_rows
    ]
    opens = [float(r.open) for r in one_rows]
    highs = [float(r.high) for r in one_rows]
    lows = [float(r.low) for r in one_rows]
    closes = [float(r.close) for r in one_rows]
    volumes = [float(r.volume or 0) for r in one_rows]
    swing_high, swing_low = prior_swings(highs, lows)
    entry = Series(
        symbol=SYMBOL,
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
    daily_times = [
        r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC)
        for r in daily_rows
    ]
    daily_closes = [float(r.close) for r in daily_rows]
    mapped: list[int | None] = []
    j = -1
    for one_time in times:
        # Only completed daily candles (decision at 1h bar close uses prior full day).
        decision_time = one_time + timedelta(hours=1)
        while j + 1 < len(daily_times) and daily_times[j + 1] + timedelta(days=1) <= decision_time:
            j += 1
        mapped.append(j if j >= 0 else None)
    return Daily1hSeries(
        entry=entry,
        atr_values=atr(highs, lows, closes),
        htf_index=mapped,
        htf_closes=daily_closes,
        htf_ema12=ema(daily_closes, 12),
        htf_ema21=ema(daily_closes, 21),
        htf_ema50=ema(daily_closes, 50),
    )


async def fetch_all(provider: BinanceSpotProvider, *, timeframe: str, start: datetime):
    out = []
    cursor = start
    step = {"1h": timedelta(hours=1), "1d": timedelta(days=1)}[timeframe]
    while True:
        batch = await provider.fetch_candles(
            provider_symbol=PROVIDER_SYMBOL,
            timeframe=timeframe,
            start=cursor,
            limit=1000,
        )
        if not batch:
            break
        out.extend(batch)
        last = batch[-1].open_time
        nxt = last + step
        if len(batch) < 1000 or nxt <= cursor:
            break
        cursor = nxt
        if len(out) > 80_000:
            break
    seen: set[datetime] = set()
    unique = []
    for c in out:
        if c.open_time in seen:
            continue
        seen.add(c.open_time)
        unique.append(c)
    return unique


async def main() -> None:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    try:
        print(f"catalog={CATALOG} fetching SOL 1h + 1d…", flush=True)
        one = await fetch_all(provider, timeframe="1h", start=start)
        daily = await fetch_all(provider, timeframe="1d", start=start)
    finally:
        await provider.aclose()
    print(
        f"bars 1h={len(one)} 1d={len(daily)} "
        f"{one[0].open_time if one else None} .. {one[-1].open_time if one else None}",
        flush=True,
    )
    series = build_series(one, daily)

    configs = [
        Daily1hWrConfig(*values)
        for values in product(
            ("stack_slope", "close50_slope"),
            (1.5, 2.0),
            (0.75, 1.0, 1.25),
            (2.5, 3.0, 4.0),
            (40, 80),
        )
    ]
    print(f"candidates={len(configs)}", flush=True)

    folds: list[TimeFold] = []
    for year in TEST_YEARS:
        folds.append(
            TimeFold(
                code=str(year),
                train_start=datetime(2021, 1, 1, tzinfo=UTC),
                train_end=datetime(year, 1, 1, tzinfo=UTC),
                test_start=datetime(year, 1, 1, tzinfo=UTC),
                test_end=datetime(year + 1, 1, 1, tzinfo=UTC),
                embargo_bars=80,
                bar_size=timedelta(hours=1),
            )
        )

    def evaluate(cfg: Daily1hWrConfig, a: datetime, b: datetime) -> ResearchPerformance:
        start_i = bisect_left(series.entry.times, a)
        end_i = bisect_left(series.entry.times, b)
        return simulate_range(series, cfg, start_i=start_i, end_i=end_i)

    policy = SelectionPolicy(
        objective=ResearchObjective.WIN_RATE,
        min_trades=40,
        min_mean_r=0.0,
        min_profit_factor=1.0,
        max_drawdown_r=20.0,
    )
    selections = run_walk_forward(
        folds=folds,
        configs=configs,
        policy=policy,
        evaluate=evaluate,
    )
    tests = [row.test for row in selections]
    combined = combine_performance(tests)
    decision = evaluate_promotion(
        tests,
        min_total_trades=80,
        min_mean_r=0.05,
        min_profit_factor=1.1,
        max_drawdown_r=20.0,
        min_positive_period_fraction=0.6,
        incumbent_mean_r=V2_MEAN_R,
        incumbent_win_rate=V2_WIN_RATE,
    )
    beat_wr = combined.win_rate > V2_WIN_RATE
    beat_mean = combined.mean_r >= V2_MEAN_R
    approved = decision.approved

    print("\n=== fold selections ===", flush=True)
    for row in selections:
        cfg = row.config
        cfg_s = (
            "WAIT"
            if cfg is None
            else (
                f"{cfg.trend} vol>={cfg.vol_threshold} "
                f"partial@{cfg.partial_r}R target={cfg.target_r}R max={cfg.max_bars}"
            )
        )
        print(
            f"{row.fold.code}: {cfg_s} | "
            f"n={row.test.trades} WR={row.test.win_rate:.1%} "
            f"mean={row.test.mean_r:+.3f} PF={row.test.profit_factor:.2f} "
            f"dd={row.test.max_drawdown_r:.2f}R"
            + (f" ({row.rejection_reason})" if row.rejection_reason else ""),
            flush=True,
        )

    print("\n=== combined walk-forward ===", flush=True)
    print(
        f"n={combined.trades} WR={combined.win_rate:.1%} "
        f"mean_R={combined.mean_r:+.3f} PF={combined.profit_factor:.2f} "
        f"dd={combined.max_drawdown_r:.2f}R",
        flush=True,
    )
    print(f"promotion_base={decision.approved} reasons={decision.reasons}", flush=True)
    print(
        f"beat_v2_wr({V2_WIN_RATE:.1%})={beat_wr} "
        f"beat_v2_mean({V2_MEAN_R:+.3f})={beat_mean}",
        flush=True,
    )
    print(f"APPROVED={approved}", flush=True)
    if not approved:
        print(
            "REJECT — do not add to registry or client picker. Keep V1/V2 only.",
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
