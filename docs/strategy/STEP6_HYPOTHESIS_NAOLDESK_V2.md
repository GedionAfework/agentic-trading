# Step 6 — NaolDesk v2: the one allowed revision (pre-registered)

Written: 2026-11-04, after v1 was REJECTED (see BACKTEST_FINDINGS).
Status: **frozen** before running. This is the **only** revision allowed for
NaolDesk; if it fails, NaolDesk stays rejected.

## Written reason for the revision

v1 applied the golden-rule exit ("entered on a bullish MSB → exit only on a
bearish MSB") to **1h** swings. The owner's framework assigns timeframes:
Weekly/Monthly = structure, **4H/Daily = setup and trend**, 1H = **entry
timing only**. The exit MSB therefore belongs on the 4H chart, where the
setup lives. v1's 1h exit fired 327 times (≈ as often as stops), consistent
with exiting on timing-level noise rather than setup-level structure.

## The single change

Replace v1 exit #3 ("Structure exit") with:

> **4H structure exit:** a completed 4h candle closes below the most recent
> confirmed 4h swing low (a 4h candle whose low is strictly lower than the 3
> candles before and 3 after; known only after those 3 close), while the
> previous 4h close was at/above it. Exit the rest at the next 1h open.

## Everything else unchanged

Entries (Setup A Breakout, Setup B Spring), stops, TP1 (1/3 at +1R, then
break-even), climax exit (1h), 720-candle safety cap, session and daily
filters, coins (BTC/ETH/SOL/DOGE/BNB), costs, fills, and all pass gates are
exactly as in [STEP6_HYPOTHESIS_NAOLDESK.md](./STEP6_HYPOTHESIS_NAOLDESK.md).

## Expectation recorded before the run

Only 42.5% (A) / 36.8% (B) of v1 trades ever reached +1R; an exit change
cannot raise that. Win rate is expected to stay far below 80% whatever the
result. The revision can at most change mean R / profit factor.
