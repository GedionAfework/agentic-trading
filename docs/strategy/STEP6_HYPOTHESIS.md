# Step 6 — Challenger hypothesis (before any search)

Written: 2026-10-08  
Catalog version: `sol-mtf-daily4h` v3  
Status: research only until nested walk-forward promotes it

## Why a new version

V1/V2 and the rejected specialist families already spent the 4h-bias / 1h-entry
idea space on 2022–2026. Step 6 may only introduce a **new catalog version**
with a genuinely unused idea. Silent edits to V1/V2 are forbidden.

## Hypothesis

**Completed daily (1d) EMA trend bias + 4h close-based BOS entry with a
volume gate can beat SOL V1 expectancy on nested walk-forward after costs.**

Rationale:

- Unused timeframe stack. Incumbents and rejected specialists used 4h → 1h.
- Daily OHLC exists for SOL from 2020-08 onward (no new data vendor).
- A prior “daily major” claim was in-sample and is not evidence; this run must
  use expanding folds, an 80-bar embargo on the **entry** timeframe (4h), and
  pair-specific SOL costs.

## What is frozen / out of scope

- Do not retune V1 or V2 parameters.
- Do not rescan BTC/ETH/BNB/FX specialist families.
- Do not promote anything into the paper soak or live-alert path from this
  script alone.
- Active soak stays on SOL V1 (`profit`) until Step 3/4 pass.

## Bounded candidate set (catalog v3)

| Knob | Allowed values |
|---|---|
| Symbol | SOL/USDT only |
| Bias TF | 1d (completed candle only) |
| Entry TF | 4h |
| HTF trend | `stack_slope`, `close50_slope` |
| Volume ratio min | 1.5, 2.0 |
| Target R | 2.0, 3.0 |
| Max bars in trade | 20, 40 (4h bars) |
| Max breakout extension | 2.0 ATR (fixed) |
| Direction | long only |
| Fills | next-open, stop-first, SOL 8 bps fill + 10 bps/side fee |

Sixteen candidates. No further knobs without a new catalog version.

## Promotion gates

Same absolute gates as prior crypto research, plus beat the profit incumbent:

| Gate | Floor |
|---|---|
| Walk-forward trades | ≥ 80 |
| Mean R | > 0.05 **and** > V1 +0.215R |
| Profit factor | > 1.1 |
| Max drawdown | ≤ 20R |
| Positive test years | ≥ 60% of years with trades |

Fail → record reject in `BACKTEST_FINDINGS.md`, leave registry empty, keep soak on V1.  
Pass → encode as paper-only challenger; still no live alerts.
