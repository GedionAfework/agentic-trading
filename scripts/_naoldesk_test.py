"""NaolDesk Step 6 test — one run of the frozen rules (simulator lives in
private_trading_backtest.naoldesk; this script only downloads and reports).

Rules: docs/strategy/STEP6_HYPOTHESIS_NAOLDESK.md (committed before this ran).
No parameters are searched here: every number below is copied from that file.

Implementation notes (clarifications, not tuning):
- "Structure exit" is a *break*: 1h close below the latest confirmed swing low
  while the previous close was at/above it (same as BOS on the way up).
- A stop is filled at min(open, stop) so overnight gaps are not flattered.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _live_sol_winrate import fetch_all  # noqa: E402
from private_trading_backtest.naoldesk import (  # noqa: E402
    Prepared,
    Trade,
    gates,
    prepare,
    row,
    simulate,
    stats,
    to_bars,
)
from private_trading_market_data.providers.binance import BinanceSpotProvider  # noqa: E402

COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "BNBUSDT")
SCORE_START = datetime(2022, 1, 1, tzinfo=UTC)
FETCH_START = datetime(2021, 6, 1, tzinfo=UTC)
YEARS = (2022, 2023, 2024, 2025, 2026)

# v1 = 1h structure exit (rejected); v2 = 4h structure exit (the one revision)
EXIT_TF = "4h" if "--v2" in sys.argv else "1h"


async def fetch_retry(provider, **kw):
    """Network retries only; never changes what data is used."""
    for attempt in range(5):
        try:
            return await fetch_all(provider, **kw)
        except Exception as exc:  # noqa: BLE001
            if attempt == 4:
                raise
            print(f"  retry {attempt + 1} after {type(exc).__name__}", flush=True)
            await asyncio.sleep(5 * (attempt + 1))


async def main() -> None:
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    prepared: dict[str, Prepared] = {}
    try:
        for pair in COINS:
            print(f"fetching {pair}…", flush=True)
            one = to_bars(await fetch_retry(provider, symbol=pair, timeframe="1h", start=FETCH_START))
            four = to_bars(await fetch_retry(provider, symbol=pair, timeframe="4h", start=FETCH_START))
            day = to_bars(await fetch_retry(provider, symbol=pair, timeframe="1d", start=FETCH_START))
            prepared[pair] = prepare(one, four, day)
            print(f"  {pair}: 1h={len(one.t)} 4h={len(four.t)} 1d={len(day.t)} "
                  f"{one.t[0]:%Y-%m-%d}..{one.t[-1]:%Y-%m-%d}", flush=True)
    finally:
        await provider.aclose()

    print("\nColumns: trades  win%  meanR  totalR  PF  maxDD  positive-years")
    print("NaolDesk " + ("v2 (4h structure exit)" if EXIT_TF == "4h" else "v1 (1h structure exit)"))
    for setup, title in (("A", "SETUP A — Breakout"), ("B", "SETUP B — Spring")):
        everything: list[Trade] = []
        print(f"\n===== {title} =====")
        for pair in COINS:
            ts = simulate(pair[:-4], prepared[pair], setup, exit_tf=EXIT_TF)
            everything += ts
            s = stats(ts)
            fails = gates(s, pooled=False)
            print(row(pair[:-4], s) + ("   PASS" if not fails else "   fail: " + "; ".join(fails)))
        pooled = stats(everything)
        fails = gates(pooled, pooled=True)
        print(row("ALL COINS", pooled) + ("   PASS" if not fails else "   fail: " + "; ".join(fails)))
        if everything:
            reasons = Counter(t.reason for t in everything)
            tp1 = sum(t.tp1 for t in everything) / len(everything)
            wins = [t.r for t in everything if t.r > 0]
            losses = [t.r for t in everything if t.r <= 0]
            print(f"  exits: {dict(reasons)}  ·  reached TP1: {100 * tp1:.1f}%")
            print(f"  avg win {sum(wins) / max(1, len(wins)):+.3f}R  ·  "
                  f"avg loss {sum(losses) / max(1, len(losses)):+.3f}R")
            print("  by year (all coins):")
            for y in YEARS:
                ys = stats([t for t in everything if t.exit_time.year == y])
                print("   " + row(str(y), ys))


if __name__ == "__main__":
    asyncio.run(main())
