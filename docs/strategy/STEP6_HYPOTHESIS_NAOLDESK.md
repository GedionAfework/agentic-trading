# Step 6 — NaolDesk hypothesis (pre-registered, before any test)

Written: 2026-11-04 · Status: **frozen** · Research only until it passes.
Source: owner's NaolDesk Strategy Document + Complete Guide (Wyckoff + HDM +
AMT). Rule choices confirmed by the owner on 2026-11-04.

These rules are fixed **before** any data is run. No knob below may be
changed after seeing results. One run, one report. A failed result may be
revised **once**, with a written reason, as a new version.

## What is new vs. already-tested work

Already tested (not repeated): fixed-R exits, retest entry, V2 scale-out
settings, BTC regime filter. New here: structure-break exit, impulse-candle
stop with ATR buffer, session filter, climax exit, Spring entry, BNB.

## Universe and data

- Coins: BTC, ETH, SOL, DOGE, BNB (USDT spot, Binance). Long only.
- Period scored: 2022-01-01 → 2026-11-03 (warm-up data before 2022 allowed).
- Timeframes: 1h (signals/exits), 4h (Spring range), 1d (trend filter).
- Only completed candles are used at every decision.

## Shared definitions

- **ATR1h / ATR4h**: 14-period average true range on that timeframe.
- **VolMA20**: mean volume of the **previous 20** 1h candles (current excluded).
- **Swing high/low (1h)**: a candle whose high (low) is strictly higher (lower)
  than the 3 candles before and 3 after. Known only after those 3 candles close.
- **Daily downtrend** (blocks longs): last completed daily close < daily EMA50
  **and** EMA50 < EMA50 ten days earlier. Anything else = not down.
- **Session filter**: entry candle opens Mon–Fri UTC and not 22:00–23:59 UTC.
- **One position per coin**; signals while in a trade are ignored.
- **Costs**: 6 bps adverse fill on every entry/exit + 10 bps fee per side.
- **Fills**: next candle open after a signal; stop and TP1 intrabar; when one
  candle touches both stop and TP1, the **stop is assumed first**.

## Setup A — Breakout (aggressive entry, managed by structure)

Signal on 1h candle *i* close, all true:

1. BOS: close[i] > most recent confirmed swing high, and close[i−1] ≤ it
   (first close above). Each swing high can trigger once.
2. Impulse: close[i] > open[i].
3. Volume: volume[i] ≥ 2.0 × VolMA20.
4. Daily not in downtrend; session filter passes for the entry candle.

Entry next open. **Stop** = low[i] − 0.5 × ATR1h[i].

## Setup B — Spring (Wyckoff Phase C)

1. **Range**: the 30 completed 4h candles before the sweep candle.
   range_low = min low, range_high = max high, and
   (range_high − range_low) ≤ 6 × ATR4h.
2. **Sweep**: a 1h candle *s* with low < range_low.
3. **Recovery**: a 1h candle *r* in s…s+3 with close > range_low and
   volume ≥ 1.5 × VolMA20.
4. Daily not in downtrend; session filter passes for the entry candle.

Entry next open after *r*. **Stop** = (lowest low from s to r) − 0.5 × ATR1h[r].
One Spring per range (the same range_low cannot trigger twice).

## Exits (both setups, in priority order)

1. **Stop** hit intrabar → exit remaining size at the stop.
2. **TP1**: price reaches entry + 1R → close **1/3** there; stop on the rest
   moves to **break-even** (entry).
3. **Structure exit** (golden rule): a 1h close below the most recent
   confirmed swing low → exit the rest at next open.
4. **Climax exit**: while close > entry, a 1h candle with volume ≥ 2.0 ×
   VolMA20 **and** range (high − low) < 0.6 × ATR1h (high effort, small
   result) → exit the rest at next open.
5. **Safety cap**: 720 1h candles (30 days) → exit at close.

R = realized P&L after costs ÷ (entry − initial stop). Win = R > 0.

## Pass gates (decided now)

Owner targets, per setup, all coins pooled:

| Gate | Floor |
|---|---|
| Trades | ≥ 150 |
| Win rate | ≥ 80% |
| Mean R | ≥ +0.25R |

Plus the roadmap absolute gates on the pooled result: profit factor > 1.1,
max drawdown ≤ 20R, ≥ 60% of years positive.

A coin can only be used if its own result (≥ 30 trades) has win rate ≥ 80%,
mean R ≥ +0.25R, PF > 1.1, and DD ≤ 20R.

**Pass** → paper-only model for the passing coins, soaked like SOL V1; live
alerts stay blocked. **Fail** → record in BACKTEST_FINDINGS, keep WAIT; one
revision allowed with a written reason.

Note: 2022–2026 has been used for other SOL/DOGE work, but these rules were
not derived from it. A pass still needs forward paper confirmation.
