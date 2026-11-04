# Step 6 — Challenger hypothesis v4 (before any search)

Written: 2026-10-22  
Catalog version: `sol-mtf-daily1h-scaleout` v4  
Status: research only until nested walk-forward promotes it

## Why a new version

V1/V2 spent **4h → 1h**. Step 6 v3 spent **1d → 4h** (REJECT: 42 trades).  
Silent edits to V1/V2 scale-out knobs on the same entries are forbidden.

## Hypothesis

**Completed daily (1d) EMA trend bias + 1h BOS/volume entry + early scale-out
can beat SOL V2 win rate on nested walk-forward after costs.**

Rationale:

- Unused timeframe stack (1d bias → 1h entry).
- Scale-out is allowed here because the **entry stack is new**, not a V2 retune.
- Goal is client “better win-rate” choice only if gates pass.

## Bounded candidate set (catalog v4)

| Knob | Allowed values |
|---|---|
| Symbol | SOL/USDT only |
| Bias TF | 1d (completed candle only) |
| Entry TF | 1h |
| HTF trend | `stack_slope`, `close50_slope` |
| Volume ratio min | 1.5, 2.0 |
| Partial at R | 0.75, 1.0, 1.25 |
| Final target R | 2.5, 3.0, 4.0 |
| Max bars | 40, 80 |
| Max breakout extension | 2.0 ATR (fixed) |
| BE after partial | always true |
| Direction | long only |

## Promotion gates (beat V2 win-rate)

| Gate | Floor |
|---|---|
| Walk-forward trades | ≥ 80 |
| Win rate | > V2 **58.9%** |
| Mean R | > 0.05 **and** ≥ V2 +0.059R |
| Profit factor | > 1.1 |
| Max drawdown | ≤ 20R |
| Positive test years | ≥ 60% of years with trades |

Fail → record reject; keep client on V1/V2 only.  
Pass → paper-only third profile; still no live alerts.
