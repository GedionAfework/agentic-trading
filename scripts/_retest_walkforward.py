"""Walk-forward research for a higher-win-rate BOS retest entry.

The method is intentionally different from the impulse-entry challenger:
after a high-volume close above structure, it waits for a low-volume retest
that holds the broken level. Configurations are selected on prior years only.
"""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import product

from _mtf_oos_search import MtfSeries, htf_passes, load_series
from _oos_strategy_search import adverse_entry, adverse_exit
from _walkforward_challenger import (
    ChallengerConfig,
    atr,
    btc_regime_by_time,
)
from _walkforward_challenger import (
    simulate_year as simulate_impulse_year,
)
from private_trading_db.session import dispose_engine, get_session_factory

SYMBOL = "SOL/USDT"
TEST_YEARS = (2022, 2023, 2024, 2025, 2026)


@dataclass(slots=True, frozen=True)
class RetestConfig:
    htf_trend: str
    bos_volume_min: float
    retest_bars: int
    retest_tolerance_atr: float
    retest_volume_max: float
    require_bullish_rejection: bool
    rr: float
    max_bars: int


@dataclass(slots=True)
class Performance:
    outcomes: list[float] = field(default_factory=list)

    @property
    def trades(self) -> int:
        return len(self.outcomes)

    @property
    def wins(self) -> int:
        return sum(value > 0 for value in self.outcomes)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def mean_r(self) -> float:
        return sum(self.outcomes) / self.trades if self.trades else 0.0

    @property
    def max_drawdown_r(self) -> float:
        equity = peak = drawdown = 0.0
        for value in self.outcomes:
            equity += value
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return drawdown

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(value for value in self.outcomes if value > 0)
        gross_loss = -sum(value for value in self.outcomes if value < 0)
        return gross_profit / gross_loss if gross_loss else float("inf")

    def add(self, value: float) -> None:
        self.outcomes.append(value)


def combine(items: list[Performance]) -> Performance:
    return Performance([value for item in items for value in item.outcomes])


def year_bounds(times: list[datetime], year: int) -> tuple[int, int]:
    return (
        bisect_left(times, datetime(year, 1, 1, tzinfo=UTC)),
        bisect_left(times, datetime(year + 1, 1, 1, tzinfo=UTC)),
    )


def simulate_year(
    series: MtfSeries,
    cfg: RetestConfig,
    *,
    year: int,
    atr_values: list[float | None],
) -> Performance:
    bars = series.entry
    start, end = year_bounds(bars.times, year)
    result = Performance()
    if end - start < 100:
        return result

    seen: set[tuple[int, float]] = set()
    setup: dict[str, float | int] | None = None
    pending: dict[str, float | int] | None = None
    trade: dict[str, float | int] | None = None

    for i in range(start, end):
        if pending is not None and i == int(pending["entry_i"]):
            entry = adverse_entry(bars.opens[i])
            stop = float(pending["stop"])
            risk = entry - stop
            if risk > 0:
                trade = {
                    "entry_i": i,
                    "entry": entry,
                    "stop": stop,
                    "initial_risk": risk,
                    "target": entry + risk * cfg.rr,
                }
            pending = None

        if trade is not None:
            stop = float(trade["stop"])
            target = float(trade["target"])
            exit_raw: float | None = None
            if bars.lows[i] <= stop:  # Conservative on same-bar ambiguity.
                exit_raw = stop
            elif bars.highs[i] >= target:
                exit_raw = target
            elif i - int(trade["entry_i"]) >= cfg.max_bars or i == end - 1:
                exit_raw = bars.closes[i]
            if exit_raw is not None:
                entry = float(trade["entry"])
                risk = float(trade["initial_risk"])
                exit_fill = adverse_exit(exit_raw)
                fees = entry * 0.001 + exit_fill * 0.001
                result.add((exit_fill - entry - fees) / risk)
                trade = None

        if trade is not None or pending is not None or i >= end - 1:
            continue

        atr_value = atr_values[i]
        volume_ratio = bars.vol_ratio[i]
        if atr_value is None or volume_ratio is None:
            continue

        if setup is not None:
            if i > int(setup["expires_i"]):
                setup = None
            else:
                level = float(setup["level"])
                tolerance = cfg.retest_tolerance_atr * atr_value
                touched = bars.lows[i] <= level + tolerance
                held = bars.lows[i] >= level - tolerance and bars.closes[i] >= level
                quiet = volume_ratio <= cfg.retest_volume_max
                bullish = bars.closes[i] > bars.opens[i]
                if (
                    touched
                    and held
                    and quiet
                    and (bullish or not cfg.require_bullish_rejection)
                    and htf_passes(series, i, cfg.htf_trend)
                ):
                    pending = {
                        "entry_i": i + 1,
                        "stop": float(setup["stop"]),
                    }
                    setup = None
                    continue

        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        if setup is not None or swing_hi is None or swing_lo is None:
            continue
        if swing_hi in seen:
            continue
        if bars.closes[i] <= swing_hi[1] or volume_ratio < cfg.bos_volume_min:
            continue
        if not htf_passes(series, i, cfg.htf_trend):
            continue
        if swing_lo[1] >= swing_hi[1]:
            continue
        seen.add(swing_hi)
        setup = {
            "level": swing_hi[1],
            "stop": swing_lo[1],
            "expires_i": min(i + cfg.retest_bars, end - 2),
        }
    return result


def score(result: Performance) -> float:
    """Balance expectancy and win rate, with a sample-size penalty."""
    return result.mean_r + 0.25 * result.win_rate - 1.0 / result.trades**0.5


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series = await load_series(session, SYMBOL)
    atr_values = atr(series.entry.highs, series.entry.lows, series.entry.closes)

    configs = [
        RetestConfig(*values)
        for values in product(
            ("stack", "stack_slope"),
            (1.5, 2.0),
            (12, 24),
            (0.25, 0.5),
            (0.8, 1.0),
            (False, True),
            (1.0, 1.5, 2.0),
            (40, 80),
        )
    ]
    years = range(2018, 2027)
    cache = {
        (cfg, year): simulate_year(
            series,
            cfg,
            year=year,
            atr_values=atr_values,
        )
        for cfg in configs
        for year in years
    }

    selections: list[tuple[int, RetestConfig, Performance, Performance]] = []
    for test_year in TEST_YEARS:
        ranked: list[tuple[float, RetestConfig, Performance]] = []
        for cfg in configs:
            train = combine([cache[(cfg, year)] for year in range(2018, test_year)])
            if train.trades < 35 or train.mean_r <= 0:
                continue
            ranked.append((score(train), cfg, train))
        ranked.sort(key=lambda row: row[0], reverse=True)
        if not ranked:
            continue
        _, winner, train = ranked[0]
        selections.append((test_year, winner, train, cache[(winner, test_year)]))

    print("Retest yearly walk-forward (selected using prior years only):", flush=True)
    for year, cfg, train, test in selections:
        print(
            f"{year} {cfg} train n={train.trades} WR={train.win_rate:.1%} "
            f"mean={train.mean_r:.3f} -> test n={test.trades} "
            f"WR={test.win_rate:.1%} mean={test.mean_r:.3f} "
            f"PF={test.profit_factor:.2f} DD={test.max_drawdown_r:.2f}R",
            flush=True,
        )
    total = combine([test for _, _, _, test in selections])
    print(
        f"\nRetest walk-forward total n={total.trades} WR={total.win_rate:.1%} "
        f"mean={total.mean_r:.3f} PF={total.profit_factor:.2f} "
        f"DD={total.max_drawdown_r:.2f}R",
        flush=True,
    )

    baseline_cfg = ChallengerConfig(
        htf_trend="stack_slope",
        vol_threshold=2.0,
        rr=3.0,
        max_bars=80,
        max_extension_atr=2.0,
        btc_filter=False,
        breakeven_at_1r=False,
    )
    btc_regime = btc_regime_by_time(series, baseline_cfg.htf_trend)
    baseline = [
        simulate_impulse_year(
            series,
            baseline_cfg,
            year=year,
            atr_values=atr_values,
            btc_regime=btc_regime,
        )
        for year in TEST_YEARS
    ]
    baseline_trades = sum(item.trades for item in baseline)
    baseline_wins = sum(item.wins for item in baseline)
    baseline_r = sum(item.r_sum for item in baseline)
    print(
        f"Impulse baseline n={baseline_trades} "
        f"WR={baseline_wins / baseline_trades:.1%} "
        f"mean={baseline_r / baseline_trades:.3f}",
        flush=True,
    )

    # This is the deployable candidate for the next paper period: selected
    # without using 2026 outcomes, then scored once on 2026.
    final_rows: list[tuple[float, RetestConfig, Performance]] = []
    for cfg in configs:
        train = combine([cache[(cfg, year)] for year in range(2018, 2026)])
        if train.trades >= 60 and train.mean_r > 0:
            final_rows.append((score(train), cfg, train))
    final_rows.sort(key=lambda row: row[0], reverse=True)
    _, final_cfg, final_train = final_rows[0]
    final_test = cache[(final_cfg, 2026)]
    print(
        f"\nFinal pre-2026 selection: {final_cfg}\n"
        f"train n={final_train.trades} WR={final_train.win_rate:.1%} "
        f"mean={final_train.mean_r:.3f}; untouched 2026 n={final_test.trades} "
        f"WR={final_test.win_rate:.1%} mean={final_test.mean_r:.3f} "
        f"PF={final_test.profit_factor:.2f} DD={final_test.max_drawdown_r:.2f}R",
        flush=True,
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
