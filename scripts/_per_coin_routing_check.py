"""Success rate of per-coin model routing vs the current single-objective routing.

INFORMATIONAL ONLY (2022-2026 is spent). No parameters are searched: the
frozen SOL V1, SOL V2 and DOGE V1 configs are replayed trade-by-trade so
coins can be combined into one portfolio ordered by exit time.

Validation first: the trade-level replay must reproduce the registry totals
(SOL V1 164 / 40.9% / +0.215R; fixed SOL V2 163 / 54.0% / +0.158R). If it does not,
the routing comparison is not printed.

Routings compared:
  A  profit profile (today):          SOL V1 + DOGE V1
  B  win_rate profile (today):        SOL V2 only (DOGE has no win_rate model -> WAIT)
  C  win_rate profile, per-coin:      SOL V2 + DOGE V1   (proposed change)
Portfolio gate is non-binding here: one position per coin at 0.5% risk, so
SOL+DOGE fit the 1% crypto cap together.
"""

from __future__ import annotations

import asyncio
import sys
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _live_sol_winrate import build_mtf, fetch_all  # noqa: E402
from _mtf_oos_search import htf_passes  # noqa: E402
from _oos_strategy_search import adverse_entry, adverse_exit  # noqa: E402
from _walkforward_challenger import atr  # noqa: E402
from private_trading_market_data.providers.binance import BinanceSpotProvider  # noqa: E402

YEARS = (2022, 2023, 2024, 2025, 2026)
RISK_PCT = 0.5


@dataclass(slots=True, frozen=True)
class Trade:
    model: str
    entry_time: datetime
    exit_time: datetime
    r: float


def _bounds(times, year):
    return (
        bisect_left(times, datetime(year, 1, 1, tzinfo=UTC)),
        bisect_left(times, datetime(year + 1, 1, 1, tzinfo=UTC)),
    )


def _signal(series, i, atr_values, seen):
    """Shared V1/V2/DOGE entry: 4h stack_slope, 1h close BOS, vol>=2, <=2 ATR."""
    bars = series.entry
    hi, lo, vr, a = bars.swing_high[i], bars.swing_low[i], bars.vol_ratio[i], atr_values[i]
    if hi is None or lo is None or vr is None or not a or hi in seen:
        return None
    close = bars.closes[i]
    if close <= hi[1] or vr < 2.0:
        return None
    if not htf_passes(series, i, "stack_slope"):
        return None
    if (close - hi[1]) / a > 2.0:
        return None
    return hi, lo, close


def replay_binary(series, atr_values, *, model: str, rr=3.0, max_bars=80) -> list[Trade]:
    """Exact copy of _walkforward_challenger.simulate_year (btc_filter off, no BE)."""
    bars = series.entry
    out: list[Trade] = []
    for year in YEARS:
        start, end = _bounds(bars.times, year)
        if end - start < 100:
            continue
        seen: set = set()
        open_trade = None
        pending = None
        for i in range(start, end):
            if open_trade is not None:
                stop, target = open_trade["stop"], open_trade["target"]
                entry = open_trade["entry"]
                risk = entry - open_trade["original_stop"]
                exit_raw = None
                if bars.lows[i] <= stop:
                    exit_raw = stop
                elif bars.highs[i] >= target:
                    exit_raw = target
                elif i - open_trade["entry_i"] >= max_bars:
                    exit_raw = bars.closes[i]
                if exit_raw is not None:
                    fill = adverse_exit(exit_raw)
                    cogs = entry * 0.001 + fill * 0.001
                    r = (fill - entry - cogs) / risk if risk > 0 else 0.0
                    out.append(Trade(model, bars.times[open_trade["entry_i"]], bars.times[i], r))
                    open_trade = None
            if pending is not None and open_trade is None and i == pending["entry_i"]:
                open_trade = {**pending, "entry": adverse_entry(bars.opens[i]),
                              "original_stop": pending["stop"]}
                pending = None
            if open_trade is not None or pending is not None or i >= end - 1:
                continue
            sig = _signal(series, i, atr_values, seen)
            if sig is None:
                continue
            hi, lo, close = sig
            stop = lo[1]
            risk = close - stop
            if risk <= 0:
                continue
            seen.add(hi)
            pending = {"entry_i": i + 1, "stop": stop, "target": close + risk * rr}
    return out


def replay_scale_out(series, atr_values, *, model: str, partial_at_r=1.25,
                     partial_fraction=0.5, runner_r=4.0, max_bars=80) -> list[Trade]:
    """Exact copy of _scaleout_walkforward.simulate_year."""
    bars = series.entry
    out: list[Trade] = []
    for year in YEARS:
        start, end = _bounds(bars.times, year)
        if end - start < 100:
            continue
        seen: set = set()
        pending = None
        trade = None
        for i in range(start, end):
            if pending is not None and i == pending["entry_i"]:
                entry = adverse_entry(bars.opens[i])
                stop = pending["stop"]
                risk = entry - stop
                if risk > 0:
                    trade = {"entry_i": i, "entry": entry, "stop": stop, "risk": risk,
                             "partial_target": entry + partial_at_r * risk,
                             "runner_target": entry + runner_r * risk,
                             "partial_taken": False, "realized_gross": 0.0, "exit_fees": 0.0}
                pending = None
            if trade is not None:
                entry, risk, stop = trade["entry"], trade["risk"], trade["stop"]
                partial_taken = trade["partial_taken"]
                remaining = 1.0 - partial_fraction if partial_taken else 1.0
                final_raw = None
                if bars.lows[i] <= stop:
                    final_raw = stop
                elif not partial_taken and bars.highs[i] >= trade["partial_target"]:
                    pf = adverse_exit(trade["partial_target"])
                    trade["realized_gross"] = partial_fraction * (pf - entry)
                    trade["exit_fees"] = partial_fraction * pf * 0.001
                    trade["partial_taken"] = True
                    trade["stop"] = entry
                    remaining = 1.0 - partial_fraction
                    if bars.highs[i] >= trade["runner_target"]:
                        final_raw = trade["runner_target"]
                elif partial_taken and bars.highs[i] >= trade["runner_target"]:
                    final_raw = trade["runner_target"]
                elif i - trade["entry_i"] >= max_bars or i == end - 1:
                    final_raw = bars.closes[i]
                if final_raw is not None:
                    ff = adverse_exit(final_raw)
                    gross = trade["realized_gross"] + remaining * (ff - entry)
                    fees = entry * 0.001 + trade["exit_fees"] + remaining * ff * 0.001
                    out.append(Trade(model, bars.times[trade["entry_i"]], bars.times[i],
                                     (gross - fees) / risk))
                    trade = None
            if trade is not None or pending is not None or i >= end - 1:
                continue
            sig = _signal(series, i, atr_values, seen)
            if sig is None:
                continue
            hi, lo, close = sig
            if lo[1] >= close:
                continue
            seen.add(hi)
            pending = {"entry_i": i + 1, "stop": lo[1]}
    return out


def stats(trades: list[Trade]) -> dict:
    ordered = sorted(trades, key=lambda t: t.exit_time)
    rs = [t.r for t in ordered]
    n = len(rs)
    if not n:
        return {"n": 0}
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    years = {t.exit_time.year for t in ordered}
    pos_years = sum(
        1 for y in years if sum(t.r for t in ordered if t.exit_time.year == y) > 0
    )
    span_months = max(
        1.0, (ordered[-1].exit_time - ordered[0].entry_time).days / 30.44
    )
    return {
        "n": n,
        "win": sum(r > 0 for r in rs) / n,
        "mean": sum(rs) / n,
        "total": sum(rs),
        "pf": gains / losses if losses else float("inf"),
        "dd": dd,
        "pos_years": f"{pos_years}/{len(years)}",
        "per_month": n / span_months,
    }


def line(name: str, s: dict) -> str:
    if not s["n"]:
        return f"{name:<34} no trades"
    return (
        f"{name:<34}{s['n']:>5}  {100 * s['win']:>5.1f}%  {s['mean']:>+7.3f}R  "
        f"{s['total']:>+7.1f}R  PF {s['pf']:>4.2f}  DD {s['dd']:>5.1f}R  "
        f"yrs+ {s['pos_years']}  {s['per_month']:>4.1f}/mo  "
        f"≈{s['total'] * RISK_PCT:+.0f}% eq"
    )


async def main() -> None:
    start = datetime(2022, 1, 1, tzinfo=UTC)
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    series = {}
    try:
        for pair, symbol in (("SOLUSDT", "SOL/USDT"), ("DOGEUSDT", "DOGE/USDT")):
            print(f"fetching {pair}…", flush=True)
            one = await fetch_all(provider, symbol=pair, timeframe="1h", start=start)
            four = await fetch_all(provider, symbol=pair, timeframe="4h", start=start)
            series[symbol] = build_mtf(one, four, symbol=symbol)
    finally:
        await provider.aclose()

    sol, doge = series["SOL/USDT"], series["DOGE/USDT"]
    sol_atr = atr(sol.entry.highs, sol.entry.lows, sol.entry.closes)
    doge_atr = atr(doge.entry.highs, doge.entry.lows, doge.entry.closes)
    sol_v1 = replay_binary(sol, sol_atr, model="SOL V1")
    sol_v2 = replay_scale_out(sol, sol_atr, model="SOL V2")
    doge_v1 = replay_binary(doge, doge_atr, model="DOGE V1")

    print("\n== Validation vs registry ==")
    ok = True
    for name, trades, (n, wr, mr) in (
        ("SOL V1", sol_v1, (164, 0.409, 0.215)),
        # Fixed V2 config across 2022-2026 (BACKTEST_FINDINGS 2026-10-08). The
        # registry's 175 / 58.9% / +0.059R is the per-year-selected walk-forward.
        ("SOL V2", sol_v2, (163, 0.540, 0.158)),
    ):
        s = stats(trades)
        match = s["n"] == n and abs(s["win"] - wr) < 0.0015 and abs(s["mean"] - mr) < 0.0015
        ok = ok and match
        print(f"{name}: {s['n']} / {100 * s['win']:.1f}% / {s['mean']:+.3f}R "
              f"(reference {n} / {100 * wr:.1f}% / {mr:+.3f}R) {'OK' if match else 'MISMATCH'}")
    if not ok:
        print("Replay does not reproduce the registry; not comparing routings.")
        return

    print("\nColumns: trades  win%  meanR  totalR  PF  maxDD  positive-years  "
          "trades/month  ≈equity at 0.5%/trade")
    print("\n== Per model ==")
    for name, trades in (("SOL V1", sol_v1), ("SOL V2", sol_v2), ("DOGE V1", doge_v1)):
        print(line(name, stats(trades)))

    print("\n== Routings (portfolio, ordered by exit time) ==")
    print(line("A profit: SOL V1 + DOGE V1", stats(sol_v1 + doge_v1)))
    print(line("B win_rate today: SOL V2 only", stats(sol_v2)))
    print(line("C win_rate per-coin: SOL V2+DOGE V1", stats(sol_v2 + doge_v1)))

    print("\n== By year: A | B | C  (trades, win%, meanR) ==")
    for year in YEARS:
        cells = []
        for trades in (sol_v1 + doge_v1, sol_v2, sol_v2 + doge_v1):
            ys = [t for t in trades if t.exit_time.year == year]
            s = stats(ys)
            cells.append("—" if not s["n"] else
                         f"{s['n']:>3} {100 * s['win']:>5.1f}% {s['mean']:>+6.3f}")
        print(f"{year}  " + "  |  ".join(f"{c:<20}" for c in cells))

    both = 0
    for d in doge_v1:
        if any(s.entry_time < d.exit_time and d.entry_time < s.exit_time for s in sol_v2):
            both += 1
    print(f"\nDOGE V1 trades overlapping an open SOL V2 trade: {both}/{len(doge_v1)} "
          "(both fit the 1% crypto cap at 0.5% each).")


if __name__ == "__main__":
    asyncio.run(main())
