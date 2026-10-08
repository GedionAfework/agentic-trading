"""Walk-forward test of partial profit-taking for the SOL impulse entry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from itertools import product

from _mtf_oos_search import htf_passes, load_series
from _oos_strategy_search import adverse_entry, adverse_exit
from _retest_walkforward import Performance, combine, year_bounds
from _walkforward_challenger import atr
from private_trading_db.session import dispose_engine, get_session_factory

SYMBOL = "SOL/USDT"
TEST_YEARS = (2022, 2023, 2024, 2025, 2026)


@dataclass(slots=True, frozen=True)
class ScaleOutConfig:
    partial_at_r: float
    partial_fraction: float
    runner_target_r: float
    max_bars: int


def simulate_year(
    series,
    cfg: ScaleOutConfig,
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
    pending: dict[str, float | int] | None = None
    trade: dict[str, float | int | bool] | None = None

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
                    "risk": risk,
                    "partial_target": entry + cfg.partial_at_r * risk,
                    "runner_target": entry + cfg.runner_target_r * risk,
                    "partial_taken": False,
                    "realized_gross": 0.0,
                    "exit_fees": 0.0,
                }
            pending = None

        if trade is not None:
            entry = float(trade["entry"])
            risk = float(trade["risk"])
            stop = float(trade["stop"])
            partial_taken = bool(trade["partial_taken"])
            remaining = 1.0 - cfg.partial_fraction if partial_taken else 1.0
            final_exit_raw: float | None = None

            if bars.lows[i] <= stop:
                final_exit_raw = stop
            elif not partial_taken and bars.highs[i] >= float(trade["partial_target"]):
                partial_fill = adverse_exit(float(trade["partial_target"]))
                trade["realized_gross"] = cfg.partial_fraction * (
                    partial_fill - entry
                )
                trade["exit_fees"] = cfg.partial_fraction * partial_fill * 0.001
                trade["partial_taken"] = True
                trade["stop"] = entry
                partial_taken = True
                remaining = 1.0 - cfg.partial_fraction
                if bars.highs[i] >= float(trade["runner_target"]):
                    final_exit_raw = float(trade["runner_target"])
            elif partial_taken and bars.highs[i] >= float(trade["runner_target"]):
                final_exit_raw = float(trade["runner_target"])
            elif i - int(trade["entry_i"]) >= cfg.max_bars or i == end - 1:
                final_exit_raw = bars.closes[i]

            if final_exit_raw is not None:
                final_fill = adverse_exit(final_exit_raw)
                gross = float(trade["realized_gross"]) + remaining * (
                    final_fill - entry
                )
                fees = (
                    entry * 0.001
                    + float(trade["exit_fees"])
                    + remaining * final_fill * 0.001
                )
                result.add((gross - fees) / risk)
                trade = None

        if trade is not None or pending is not None or i >= end - 1:
            continue
        swing_hi = bars.swing_high[i]
        swing_lo = bars.swing_low[i]
        volume_ratio = bars.vol_ratio[i]
        atr_value = atr_values[i]
        if (
            swing_hi is None
            or swing_lo is None
            or volume_ratio is None
            or atr_value is None
            or swing_hi in seen
        ):
            continue
        close = bars.closes[i]
        if close <= swing_hi[1] or volume_ratio < 2.0:
            continue
        if not htf_passes(series, i, "stack_slope"):
            continue
        if (close - swing_hi[1]) / atr_value > 2.0:
            continue
        if swing_lo[1] >= close:
            continue
        seen.add(swing_hi)
        pending = {"entry_i": i + 1, "stop": swing_lo[1]}
    return result


def score(result: Performance) -> float:
    return result.mean_r + 0.3 * result.win_rate - 1.0 / result.trades**0.5


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series = await load_series(session, SYMBOL)
    atr_values = atr(series.entry.highs, series.entry.lows, series.entry.closes)
    configs = [
        ScaleOutConfig(*values)
        for values in product(
            (0.75, 1.0, 1.25),
            (0.5, 0.67, 0.8),
            (2.0, 3.0, 4.0),
            (40, 80),
        )
    ]
    cache = {
        (cfg, year): simulate_year(
            series,
            cfg,
            year=year,
            atr_values=atr_values,
        )
        for cfg in configs
        for year in range(2018, 2027)
    }

    selected: list[tuple[int, ScaleOutConfig, Performance, Performance]] = []
    for test_year in TEST_YEARS:
        ranked: list[tuple[float, ScaleOutConfig, Performance]] = []
        for cfg in configs:
            train = combine([cache[(cfg, year)] for year in range(2018, test_year)])
            if train.trades >= 50 and train.mean_r > 0:
                ranked.append((score(train), cfg, train))
        ranked.sort(key=lambda row: row[0], reverse=True)
        if not ranked:
            continue
        _, winner, train = ranked[0]
        selected.append((test_year, winner, train, cache[(winner, test_year)]))

    print("Scale-out yearly walk-forward (selected using prior years only):")
    for year, cfg, train, test in selected:
        print(
            f"{year} {cfg} train n={train.trades} WR={train.win_rate:.1%} "
            f"mean={train.mean_r:.3f} -> test n={test.trades} "
            f"WR={test.win_rate:.1%} mean={test.mean_r:.3f} "
            f"PF={test.profit_factor:.2f} DD={test.max_drawdown_r:.2f}R"
        )
    total = combine([test for _, _, _, test in selected])
    print(
        f"\nScale-out walk-forward total n={total.trades} "
        f"WR={total.win_rate:.1%} mean={total.mean_r:.3f} "
        f"PF={total.profit_factor:.2f} DD={total.max_drawdown_r:.2f}R"
    )

    binary_cfg = ScaleOutConfig(
        partial_at_r=3.0,
        partial_fraction=0.0,
        runner_target_r=3.0,
        max_bars=80,
    )
    binary = combine(
        [
            simulate_year(
                series,
                binary_cfg,
                year=year,
                atr_values=atr_values,
            )
            for year in TEST_YEARS
        ]
    )
    print(
        f"Comparable binary 3R baseline n={binary.trades} "
        f"WR={binary.win_rate:.1%} mean={binary.mean_r:.3f} "
        f"PF={binary.profit_factor:.2f} DD={binary.max_drawdown_r:.2f}R"
    )

    final_rows: list[tuple[float, ScaleOutConfig, Performance]] = []
    for cfg in configs:
        train = combine([cache[(cfg, year)] for year in range(2018, 2026)])
        if train.trades >= 100 and train.mean_r > 0:
            final_rows.append((score(train), cfg, train))
    final_rows.sort(key=lambda row: row[0], reverse=True)
    _, final_cfg, final_train = final_rows[0]
    final_test = cache[(final_cfg, 2026)]
    print(
        f"\nFinal pre-2026 selection: {final_cfg}\n"
        f"train n={final_train.trades} WR={final_train.win_rate:.1%} "
        f"mean={final_train.mean_r:.3f}; untouched 2026 n={final_test.trades} "
        f"WR={final_test.win_rate:.1%} mean={final_test.mean_r:.3f} "
        f"PF={final_test.profit_factor:.2f} DD={final_test.max_drawdown_r:.2f}R"
    )
    print("Fixed final candidate by year:")
    fixed_years: list[Performance] = []
    for year in TEST_YEARS:
        one = cache[(final_cfg, year)]
        fixed_years.append(one)
        print(
            f"  {year} n={one.trades} WR={one.win_rate:.1%} "
            f"mean={one.mean_r:.3f} PF={one.profit_factor:.2f} "
            f"DD={one.max_drawdown_r:.2f}R"
        )
    fixed_total = combine(fixed_years)
    binary_2026 = simulate_year(
        series,
        binary_cfg,
        year=2026,
        atr_values=atr_values,
    )
    print(
        f"Fixed candidate total n={fixed_total.trades} "
        f"WR={fixed_total.win_rate:.1%} mean={fixed_total.mean_r:.3f} "
        f"PF={fixed_total.profit_factor:.2f} DD={fixed_total.max_drawdown_r:.2f}R\n"
        f"Untouched 2026 binary baseline n={binary_2026.trades} "
        f"WR={binary_2026.win_rate:.1%} mean={binary_2026.mean_r:.3f}"
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
