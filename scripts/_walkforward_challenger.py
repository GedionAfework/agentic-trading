"""Yearly walk-forward challenger: select only on past years, test the next year."""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product

from private_trading_db.session import dispose_engine, get_session_factory

from _mtf_oos_search import MtfSeries, htf_passes, load_series
from _oos_strategy_search import Metrics, adverse_entry, adverse_exit

SYMBOLS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")
TEST_YEARS = (2022, 2023, 2024, 2025, 2026)


@dataclass(slots=True, frozen=True)
class ChallengerConfig:
    htf_trend: str
    vol_threshold: float
    rr: float
    max_bars: int
    max_extension_atr: float
    btc_filter: bool
    breakeven_at_1r: bool


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14):
    out: list[float | None] = [None] * len(closes)
    trs: list[float] = []
    running = 0.0
    for i in range(len(closes)):
        prev = closes[i - 1] if i else None
        tr = highs[i] - lows[i]
        if prev is not None:
            tr = max(tr, abs(highs[i] - prev), abs(lows[i] - prev))
        trs.append(tr)
        running += tr
        if i >= period:
            running -= trs[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def year_bounds(times: list[datetime], year: int) -> tuple[int, int]:
    start = bisect_left(times, datetime(year, 1, 1, tzinfo=UTC))
    end = bisect_left(times, datetime(year + 1, 1, 1, tzinfo=UTC))
    return start, end


def btc_regime_by_time(btc: MtfSeries, mode: str) -> dict[datetime, bool]:
    return {
        time: htf_passes(btc, i, mode)
        for i, time in enumerate(btc.entry.times)
    }


def simulate_year(
    series: MtfSeries,
    cfg: ChallengerConfig,
    *,
    year: int,
    atr_values: list[float | None],
    btc_regime: dict[datetime, bool],
) -> Metrics:
    bars = series.entry
    start, end = year_bounds(bars.times, year)
    metrics = Metrics()
    if end - start < 100:
        return metrics
    seen: set[tuple[int, float]] = set()
    open_trade: dict[str, float | int | bool] | None = None
    pending: dict[str, float | int] | None = None

    for i in range(start, end):
        if open_trade is not None:
            original_stop = float(open_trade["original_stop"])
            stop = float(open_trade["stop"])
            target = float(open_trade["target"])
            entry = float(open_trade["entry"])
            initial_risk = entry - original_stop
            if (
                cfg.breakeven_at_1r
                and not bool(open_trade["at_breakeven"])
                and bars.highs[i] >= entry + initial_risk
            ):
                stop = entry
                open_trade["stop"] = stop
                open_trade["at_breakeven"] = True
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
                exit_fill = adverse_exit(exit_raw)
                cogs = entry * 0.001 + exit_fill * 0.001
                pnl_r = (
                    (exit_fill - entry - cogs) / initial_risk if initial_risk > 0 else 0.0
                )
                metrics.add(pnl_r)
                open_trade = None

        if pending is not None and open_trade is None and i == int(pending["entry_i"]):
            entry = adverse_entry(bars.opens[i])
            open_trade = {
                **pending,
                "entry": entry,
                "original_stop": pending["stop"],
                "at_breakeven": False,
            }
            pending = None

        if open_trade is not None or pending is not None or i >= end - 1:
            continue
        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        vr = bars.vol_ratio[i]
        atr_value = atr_values[i]
        if swing_hi is None or swing_lo is None or vr is None or not atr_value:
            continue
        if swing_hi in seen:
            continue
        close = bars.closes[i]
        if close <= swing_hi[1] or vr < cfg.vol_threshold:
            continue
        if not htf_passes(series, i, cfg.htf_trend):
            continue
        if cfg.btc_filter and series.entry.symbol != "BTC/USDT":
            if not btc_regime.get(bars.times[i], False):
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
            "target": close + risk * cfg.rr,
        }
    return metrics


def combine(items: list[Metrics]) -> Metrics:
    out = Metrics()
    for item in items:
        out.trades += item.trades
        out.wins += item.wins
        out.r_sum += item.r_sum
    return out


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series = [await load_series(session, symbol) for symbol in SYMBOLS]
    atrs = {
        s.entry.symbol: atr(s.entry.highs, s.entry.lows, s.entry.closes) for s in series
    }

    configs = [
        ChallengerConfig(*values)
        for values in product(
            ("stack", "stack_slope"),
            (1.5, 2.0),
            (1.5, 2.0, 3.0),
            (40, 80),
            (0.5, 1.0, 2.0),
            (False, True),
            (False, True),
        )
    ]
    btc_regimes = {
        mode: btc_regime_by_time(series[0], mode) for mode in ("stack", "stack_slope")
    }

    # Cache every config/year/symbol result once. Walk-forward selection below
    # only aggregates years preceding the test year.
    cache: dict[tuple[ChallengerConfig, int, str], Metrics] = {}
    for cfg in configs:
        for year in range(2018, 2027):
            for item in series:
                cache[(cfg, year, item.entry.symbol)] = simulate_year(
                    item,
                    cfg,
                    year=year,
                    atr_values=atrs[item.entry.symbol],
                    btc_regime=btc_regimes[cfg.htf_trend],
                )

    walkforward: list[Metrics] = []
    selected: list[tuple[int, ChallengerConfig, Metrics, Metrics]] = []
    for test_year in TEST_YEARS:
        ranked: list[tuple[float, ChallengerConfig, Metrics]] = []
        for cfg in configs:
            train = combine(
                [
                    cache[(cfg, year, symbol)]
                    for year in range(2018, test_year)
                    for symbol in SYMBOLS
                ]
            )
            if train.trades < 150:
                continue
            score = train.mean_r - 1.0 / (train.trades**0.5)
            ranked.append((score, cfg, train))
        ranked.sort(key=lambda row: row[0], reverse=True)
        winner = ranked[0][1]
        train = ranked[0][2]
        test = combine([cache[(winner, test_year, symbol)] for symbol in SYMBOLS])
        selected.append((test_year, winner, train, test))
        walkforward.append(test)

    print("Yearly walk-forward (each row selected using earlier years only):", flush=True)
    for year, cfg, train, test in selected:
        print(
            f"{year} {cfg} train n={train.trades} mean_R={train.mean_r:.3f} -> "
            f"test n={test.trades} WR={test.win_rate:.1%} mean_R={test.mean_r:.3f}",
            flush=True,
        )
    total = combine(walkforward)
    print(
        f"\nwalkforward total n={total.trades} WR={total.win_rate:.1%} "
        f"mean_R={total.mean_r:.3f}",
        flush=True,
    )

    print("\nWalk-forward outcomes by symbol:", flush=True)
    for symbol in SYMBOLS:
        result = combine(
            [cache[(cfg, year, symbol)] for year, cfg, _train, _test in selected]
        )
        print(
            f"{symbol} n={result.trades} WR={result.win_rate:.1%} mean_R={result.mean_r:.3f}",
            flush=True,
        )
        for year, cfg, _train, _test in selected:
            one = cache[(cfg, year, symbol)]
            print(
                f"  {year} n={one.trades} WR={one.win_rate:.1%} mean_R={one.mean_r:.3f}",
                flush=True,
            )

    current = ChallengerConfig(
        htf_trend="stack_slope",
        vol_threshold=2.0,
        rr=3.0,
        max_bars=80,
        max_extension_atr=2.0,
        btc_filter=False,
        breakeven_at_1r=False,
    )
    sol = next(item for item in series if item.entry.symbol == "SOL/USDT")
    fixed_years = [
        simulate_year(
            sol,
            current,
            year=year,
            atr_values=atrs["SOL/USDT"],
            btc_regime=btc_regimes[current.htf_trend],
        )
        for year in TEST_YEARS
    ]
    fixed_total = combine(fixed_years)
    print(
        "\nFixed SOL paper-challenger candidate "
        f"n={fixed_total.trades} WR={fixed_total.win_rate:.1%} mean_R={fixed_total.mean_r:.3f}",
        flush=True,
    )
    for year, result in zip(TEST_YEARS, fixed_years, strict=True):
        print(
            f"  {year} n={result.trades} WR={result.win_rate:.1%} mean_R={result.mean_r:.3f}",
            flush=True,
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
