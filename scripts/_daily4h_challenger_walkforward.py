"""Step 6 nested walk-forward: SOL 1d bias + 4h entry challenger.

Hypothesis and gates: docs/strategy/STEP6_HYPOTHESIS.md
Does not edit V1/V2 or write to the paper registry.
"""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product

from _mtf_oos_search import candle_rows
from _oos_strategy_search import Series, ema, prior_swings, volume_ratio
from _walkforward_challenger import atr
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
from private_trading_db.models.market import Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_strategies.challenger import (
    STEP6_CATALOG_VERSION,
    V1_INCUMBENT_MEAN_R,
)
from sqlalchemy import select

SYMBOL = "SOL/USDT"
FEE_RATE = 0.001
TEST_YEARS = (2022, 2023, 2024, 2025, 2026)


@dataclass(slots=True)
class Daily4hSeries:
    entry: Series
    atr_values: list[float | None]
    htf_index: list[int | None]
    htf_closes: list[float]
    htf_ema12: list[float | None]
    htf_ema21: list[float | None]
    htf_ema50: list[float | None]


@dataclass(slots=True, frozen=True)
class Daily4hConfig:
    trend: str
    vol_threshold: float
    rr: float
    max_bars: int
    max_extension_atr: float = 2.0


def _fill(raw: float, *, entering: bool) -> float:
    bps = pair_cost_bps(SYMBOL) / 10_000.0
    return raw * (1.0 + bps) if entering else raw * (1.0 - bps)


def htf_passes(series: Daily4hSeries, i: int, mode: str) -> bool:
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


async def load_daily4h(session, symbol: str = SYMBOL) -> Daily4hSeries:
    instrument = (
        await session.execute(
            select(Instrument).where(Instrument.canonical_symbol == symbol)
        )
    ).scalar_one()
    entry_rows = await candle_rows(session, instrument.id, "4h")
    day_rows = await candle_rows(session, instrument.id, "1d")

    times = [r.open_time for r in entry_rows]
    opens = [float(r.open) for r in entry_rows]
    highs = [float(r.high) for r in entry_rows]
    lows = [float(r.low) for r in entry_rows]
    closes = [float(r.close) for r in entry_rows]
    volumes = [float(r.volume or 0) for r in entry_rows]
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

    day_times = [r.open_time for r in day_rows]
    day_closes = [float(r.close) for r in day_rows]
    mapped: list[int | None] = []
    j = -1
    for bar_time in times:
        # Only a completed daily candle may bias the 4h decision.
        decision_time = bar_time + timedelta(hours=4)
        while (
            j + 1 < len(day_times)
            and day_times[j + 1] + timedelta(days=1) <= decision_time
        ):
            j += 1
        mapped.append(j if j >= 0 else None)

    return Daily4hSeries(
        entry=entry,
        atr_values=atr(highs, lows, closes),
        htf_index=mapped,
        htf_closes=day_closes,
        htf_ema12=ema(day_closes, 12),
        htf_ema21=ema(day_closes, 21),
        htf_ema50=ema(day_closes, 50),
    )


def simulate(
    series: Daily4hSeries,
    cfg: Daily4hConfig,
    start: datetime,
    end: datetime,
) -> ResearchPerformance:
    bars = series.entry
    first = bisect_left(bars.times, start)
    last = bisect_left(bars.times, end)
    result = ResearchPerformance()
    if last - first < 50:
        return result

    seen: set[tuple[int, float]] = set()
    pending: dict[str, float | int] | None = None
    trade: dict[str, float | int] | None = None

    for i in range(first, last):
        if pending is not None and i == int(pending["entry_i"]):
            entry = _fill(bars.opens[i], entering=True)
            stop = float(pending["stop"])
            risk = entry - stop
            if risk > 0:
                trade = {
                    "entry_i": i,
                    "entry": entry,
                    "stop": stop,
                    "risk": risk,
                    "target": entry + risk * cfg.rr,
                }
            pending = None

        if trade is not None:
            stop = float(trade["stop"])
            target = float(trade["target"])
            entry = float(trade["entry"])
            risk = float(trade["risk"])
            exit_raw: float | None = None
            if bars.lows[i] <= stop:
                exit_raw = stop
            elif bars.highs[i] >= target:
                exit_raw = target
            elif i - int(trade["entry_i"]) >= cfg.max_bars or i == last - 1:
                exit_raw = bars.closes[i]
            if exit_raw is not None:
                fill = _fill(exit_raw, entering=False)
                fees = FEE_RATE * (entry + fill)
                result.outcomes_r.append((fill - entry - fees) / risk)
                trade = None

        if trade is not None or pending is not None or i >= last - 1:
            continue

        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        vr = bars.vol_ratio[i]
        atr_value = series.atr_values[i]
        if swing_hi is None or swing_lo is None or vr is None or atr_value is None:
            continue
        if swing_hi in seen:
            continue
        if bars.closes[i] <= swing_hi[1] or vr < cfg.vol_threshold:
            continue
        if not htf_passes(series, i, cfg.trend):
            continue
        extension = bars.closes[i] - swing_hi[1]
        if extension > cfg.max_extension_atr * atr_value:
            continue
        stop = swing_lo[1]
        risk = bars.closes[i] - stop
        if risk <= 0:
            continue
        seen.add(swing_hi)
        pending = {"entry_i": i + 1, "stop": stop}

    return result


def _folds() -> list[TimeFold]:
    folds: list[TimeFold] = []
    for year in TEST_YEARS:
        folds.append(
            TimeFold(
                code=str(year),
                train_start=datetime(2020, 8, 11, tzinfo=UTC),
                train_end=datetime(year, 1, 1, tzinfo=UTC),
                test_start=datetime(year, 1, 1, tzinfo=UTC),
                test_end=datetime(year + 1, 1, 1, tzinfo=UTC),
                embargo_bars=80,
                bar_size=timedelta(hours=4),
            )
        )
    return folds


def candidates() -> list[Daily4hConfig]:
    return [
        Daily4hConfig(*values)
        for values in product(
            ("stack_slope", "close50_slope"),
            (1.5, 2.0),
            (2.0, 3.0),
            (20, 40),
        )
    ]


async def main() -> None:
    print(f"Step 6 catalog={STEP6_CATALOG_VERSION} symbol={SYMBOL}", flush=True)
    factory = get_session_factory()
    async with factory() as session:
        series = await load_daily4h(session)
    print(
        f"Loaded 4h={len(series.entry.times)} 1d={len(series.htf_closes)}",
        flush=True,
    )

    configs = candidates()
    policy = SelectionPolicy(
        ResearchObjective.PROFIT,
        min_trades=30,
        min_mean_r=0.0,
        min_profit_factor=1.0,
        max_drawdown_r=20.0,
    )

    def evaluate(cfg: Daily4hConfig, start: datetime, end: datetime) -> ResearchPerformance:
        return simulate(series, cfg, start, end)

    selections = run_walk_forward(
        folds=_folds(),
        configs=configs,
        policy=policy,
        evaluate=evaluate,
    )

    print("\nPer-fold test results:", flush=True)
    test_periods: list[ResearchPerformance] = []
    for row in selections:
        if row.config is None:
            print(f"  {row.fold.code}: WAIT ({row.rejection_reason})", flush=True)
            test_periods.append(ResearchPerformance())
            continue
        test_periods.append(row.test)
        cfg = row.config
        print(
            f"  {row.fold.code}: {cfg.trend} vol>={cfg.vol_threshold} "
            f"rr={cfg.rr} max_bars={cfg.max_bars} | "
            f"n={row.test.trades} WR={row.test.win_rate:.1%} "
            f"mean_R={row.test.mean_r:+.3f} PF={row.test.profit_factor:.2f} "
            f"DD={row.test.max_drawdown_r:.2f}R",
            flush=True,
        )

    combined = combine_performance(test_periods)
    decision = evaluate_promotion(
        test_periods,
        min_total_trades=80,
        min_mean_r=0.05,
        min_profit_factor=1.1,
        max_drawdown_r=20.0,
        min_positive_period_fraction=0.6,
        incumbent_mean_r=V1_INCUMBENT_MEAN_R,
    )
    print("\nCombined walk-forward:", flush=True)
    print(
        f"  n={combined.trades} WR={combined.win_rate:.1%} "
        f"mean_R={combined.mean_r:+.3f} PF={combined.profit_factor:.2f} "
        f"DD={combined.max_drawdown_r:.2f}R "
        f"positive_years={decision.positive_period_fraction:.0%}",
        flush=True,
    )
    print(
        f"  beat_V1(+{V1_INCUMBENT_MEAN_R}): "
        f"{'yes' if combined.mean_r > V1_INCUMBENT_MEAN_R else 'no'}",
        flush=True,
    )
    print(
        f"  decision={'PASS' if decision.approved else 'REJECT'} "
        f"reasons={decision.reasons or ('none',)}",
        flush=True,
    )
    print(
        "  registry: unchanged (fail-closed; no paper/live promotion from this script)",
        flush=True,
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
