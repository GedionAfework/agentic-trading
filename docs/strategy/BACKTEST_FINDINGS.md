# Backtest findings

Measured research results only. These are not live-return claims.

## 2026-10-08 — methodology correction

The first holdout run double-counted fees: once in adverse fill prices and
again as cash costs. The engine now applies slippage + half-spread to fill
prices and charges fees separately, matching `CostModel.round_trip_bps`.
The earlier −0.222R / −0.154R values are superseded.

## 2026-10-08 — 4h trend + 1h entry out-of-sample search

- Universe: BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT
- Source: stored Binance spot 4h and 1h candles
- Selection data: bars before 2024
- Untouched evaluation: 2024 onward
- Execution: next-open, conservative stop-first ambiguity, configured costs
- Duplicate signals for the same broken structure level are suppressed
- No look-ahead: only a completed 4h candle may supply the 1h decision bias

| Configuration | Holdout trades | Win rate | Mean R |
|---|---:|---:|---:|
| 4h close > EMA50; 1h volume ≥1.5×; 2R; 40 bars | 1,222 | 42.1% | **−0.063R** |
| Best pre-2024 candidate: 4h EMA 12>21>50 with rising EMA50; 1h volume ≥2×; 3R; 80 bars | 505 | 37.2% | **−0.015R** |

The stricter candidate was nearly break-even but remained negative overall
and on BTC, ETH, and BNB; only SOL was positive (+0.114R). It must not be
promoted to production alerts.

The earlier 60.7% / +0.579R daily-major result is not sufficient evidence:
it used the full period rather than an untouched holdout and tested 1d, while
the intended timing timeframe is 1h.

## 2026-10-08 — yearly walk-forward challenger

Each test year used a configuration selected only from preceding years.
Additional candidates included BTC regime agreement, breakout-extension
limits, and break-even stop management.

The broad four-symbol challenger failed:

- 632 trades
- 33.1% win rate
- **−0.099R** mean

The fixed SOL-only candidate was materially stronger:

- Configuration: completed 4h EMA 12>21>50 with rising EMA50; 1h close-based
  BOS; volume ratio ≥2; breakout extension ≤2 ATR; 3R target; 80-bar timeout
- 164 walk-forward trades (2022–2026)
- 40.9% win rate
- **+0.215R** mean
- Positive in 2023–2026; 2022 was −0.064R

This is encoded as `SOL_MTF_CHALLENGER_V1`. It is **paper-only** and cannot
authorize live alerts. Symbol selection was informed by the four-symbol
comparison, so paper soak is required before any promotion discussion.

## 2026-10-08 — higher-win-rate alternatives

A low-volume retest-entry method was rejected: its yearly walk-forward result
was 89 trades, 39.3% wins, and −0.022R mean after costs.

A scale-out method kept the V1 entry but closed 50% at +1.25R, moved the
remainder's stop to break-even, and targeted +4R:

- Yearly walk-forward selection: 175 trades, 58.9% wins, +0.059R mean,
  1.14 profit factor, and 13.02R maximum drawdown
- Fixed candidate across 2022–2026: 163 trades, 54.0% wins, +0.158R mean
- Untouched 2026 after selection on data through 2025: 26 trades, 65.4% wins,
  +0.284R mean, and 1.76 profit factor
- Comparable binary 3R simulation: 163 trades, 38.7% wins, +0.150R mean,
  and 17.99R maximum drawdown

This is encoded as `SOL_MTF_CHALLENGER_V2_SCALE_OUT`. It improved win rate and
drawdown while remaining profitable, but did not approach 80% and has only 26
trades in the untouched 2026 slice. It remains **paper-only**.

## 2026-10-08 — core multi-market regime search

A shared embargoed walk-forward harness tested separate `profit` and
`win_rate` objectives. Crypto used completed 4h trend, 1h structure, ATR
regimes, and real Binance volume. Forex used completed daily trend, 1h
structure, ATR regimes, both directions, and no volume gate because Yahoo FX
volume is not trustworthy. Costs and conservative stop-first fills were
included.

Crypto `profit` walk-forward results:

- BTC: 155 trades, 36.8% wins, +0.081R mean, 1.14 profit factor, 15.48R
  drawdown; negative in 2022, 2025, and slightly negative in 2026
- ETH: 140 trades, −0.044R mean
- BNB: 139 trades, −0.049R mean
- SOL: 152 trades, +0.012R mean with a 1.02 profit factor
- Pooled: 586 trades, approximately +0.002R mean

Crypto `win_rate` results:

- BTC: 211 trades, 53.1% wins, +0.005R mean, 1.01 profit factor
- ETH, BNB, and SOL had negative expectancy
- Pooled: 726 trades, approximately −0.041R mean

All eight forex pairs either failed after-cost walk-forward evaluation or had
folds with no eligible training model. The pooled forex `profit` profile was
357 trades at approximately −0.278R mean; the `win_rate` profile was 424
trades at approximately −0.289R mean. AUD/USD and EUR/GBP correctly returned
`WAIT` for every fold because no candidate passed the training gates.

No new crypto or forex model was promoted. The prior SOL V1/V2 candidates
remain paper-only hypotheses, but this broader regime search did not
independently confirm a general SOL edge. Multi-market routing therefore
fails closed to `WAIT` for every unvalidated symbol/regime/objective.

## 2026-10-08 — pair-specialist family walk-forward

Pair-specific strategy families were compared under the same nested walk-forward
harness as the core regime search: expanding folds, an 80-bar embargo,
next-open fills, pair-specific slippage/spread assumptions, stop-first
ambiguity, crypto taker fees, and Yahoo FX volume treated as unknown. Crypto
used completed 4h trend plus 1h entry. Forex used completed daily trend, 1h
entry, London/New York sessions, and both directions. Selection was per
symbol, never pooled. Two objectives were scored separately: `profit`
(expectancy with drawdown and multiple-search penalties) and `win_rate`
(Wilson lower bound plus positive expectancy). Promotion required ≥80 crypto
or ≥50 forex walk-forward trades, mean R > 0.05, profit factor > 1.1,
drawdown ≤ 20R, and ≥60% positive periods. SOL specialists also had to beat
the paper incumbents (V1 +0.215R mean, V2 58.9% wins).

Walk-forward test-fold totals:

| Symbol | Objective | Trades | Win rate | Mean R | PF | Max DD | Promote |
|---|---|---:|---:|---:|---:|---:|---|
| BTC/USDT | profit | 211 | 37.0% | +0.010 | 1.02 | 19.67R | No |
| BTC/USDT | win_rate | 237 | 38.8% | −0.030 | 0.95 | 19.67R | No |
| ETH/USDT | profit | 189 | 34.4% | −0.105 | 0.82 | 24.86R | No |
| ETH/USDT | win_rate | 242 | 35.1% | −0.119 | 0.81 | 30.67R | No |
| BNB/USDT | profit | 212 | 40.1% | +0.021 | 1.04 | 17.11R | No |
| BNB/USDT | win_rate | 241 | 37.8% | −0.040 | 0.93 | 26.30R | No |
| SOL/USDT | profit | 91 | 47.3% | +0.197 | 1.44 | 6.32R | No |
| SOL/USDT | win_rate | 291 | 45.0% | +0.054 | 1.10 | 15.88R | No |
| EUR/USD | both | 60 | 38.3% | −0.028 | 0.95 | 13.25R | No |
| GBP/USD | both | 65 | 40.0% | −0.021 | 0.96 | 6.80R | No |
| USD/JPY | both | 50 | 40.0% | +0.015 | 1.03 | 10.09R | No |
| USD/CHF | both | 26 | 26.9% | −0.300 | 0.59 | 10.55R | No |
| AUD/USD | profit | 15 | 6.7% | −1.008 | 0.08 | 16.48R | No |
| AUD/USD | win_rate | 23 | 26.1% | −0.606 | 0.26 | 15.74R | No |
| USD/CAD | both | 0 | — | — | — | — | WAIT |
| NZD/USD | both | 0 | — | — | — | — | WAIT |
| EUR/GBP | both | 0 | — | — | — | — | WAIT |

Rejected, with the selected family on each test fold:

- BTC `profit`: 4h/1h trend breakout v2. Positive in 2023, 2024, and 2026
  holdout (+0.118R on 33 trades); negative in 2022 and 2025. Expectancy and
  profit factor stayed below the promotion floor.
- BTC `win_rate`: mix of breakout v1/v2; 2025 was −0.290R. Same floor miss.
- ETH: relative-strength/beta-adjusted momentum was selected only in 2023
  (`profit`, −0.353R). Remaining folds used trend breakout and were net
  negative with drawdown above 20R.
- BNB: trend continuation/breakout, not range reversion, won training
  selection. 2022 and 2025 were positive; 2023, 2024, and 2026 were not.
- SOL `profit`: +0.197R and 1.44 PF, but only two of five years were
  positive, 2024–2025 volatility-expansion folds were tiny and negative, and
  +0.197R did not beat SOL V1 (+0.215R).
- SOL `win_rate`: pullback then trend breakout, 45.0% wins and +0.054R, below
  V2’s 58.9% win rate and the 1.10 profit-factor floor.
- EUR, GBP, and USD/JPY: session breakout v2 was the only recurring
  candidate. After-cost expectancy was near zero or negative, and several
  quarterly folds had too few trades for promotion.
- USD/CHF and AUD/USD: after-cost losers; later 2026 folds returned WAIT.
- USD/CAD, NZD/USD, and EUR/GBP: no training candidate passed, so every
  fold correctly stayed WAIT.

No specialist was written into `VALIDATED_SPECIALIST_MODELS`. Runtime routing
therefore stays fail-closed: unvalidated pairs WAIT, and SOL still falls
back to the paper-only V1/V2 incumbents. Live alerts remain blocked.

## 2026-10-08 — soak Step 3 holdout definition

SOL V1 already consumed 2022–2026 in yearly walk-forward test folds, so those
years are **not** an untouched holdout. Step 3 therefore scores only closed
SOL paper trades on/after the soak freeze date `2026-10-08`, with Step 2
gates plus a competitive mean-R floor of half the research expectancy
(+0.1075R vs +0.215R). Until that post-freeze paper sample exists and passes,
the holdout decision remains `WAIT`.

## 2026-10-08 — Step 6 challenger: SOL 1d bias + 4h entry

Hypothesis: [STEP6_HYPOTHESIS.md](./STEP6_HYPOTHESIS.md). Catalog
`sol-mtf-daily4h-v3`. Unused timeframe stack vs V1/V2 (4h/1h). Sixteen
bounded candidates; nested yearly walk-forward; 80-bar embargo on 4h;
SOL pair costs + taker fees; next-open; stop-first.

Per-fold test results (selected on embargoed prior years only):

| Year | Selected | Trades | Win rate | Mean R | PF | Max DD |
|---|---|---:|---:|---:|---:|---:|
| 2022 | close50_slope vol≥1.5 rr=3 max_bars=40 | 2 | 0.0% | −0.557 | 0.00 | 1.11R |
| 2023 | close50_slope vol≥1.5 rr=3 max_bars=40 | 23 | 56.5% | +0.702 | 2.68 | 4.90R |
| 2024 | stack_slope vol≥2.0 rr=3 max_bars=20 | 10 | 60.0% | +0.286 | 1.76 | 1.70R |
| 2025 | stack_slope vol≥2.0 rr=3 max_bars=40 | 3 | 66.7% | +0.682 | 3.67 | 0.77R |
| 2026 | stack_slope vol≥2.0 rr=3 max_bars=40 | 4 | 50.0% | +0.004 | 1.01 | 1.55R |

Combined: **42 trades**, 54.8% wins, **+0.475R** mean, 2.18 PF, 4.90R DD,
80% positive years. Mean R beats V1 (+0.215R), but total trades miss the ≥80
floor.

**Decision: REJECT** (`insufficient_total_trades`). Spec
`SOL_MTF_CHALLENGER_V3_DAILY4H` stays research-only. Not added to
`PAPER_MODEL_REGISTRY` or `VALIDATED_SPECIALIST_MODELS`. Active soak remains
SOL V1. Do not lower the trade-count gate to force a promote.

## 2026-10-13 — Owner coin set + DOGE nested walk-forward

Owner publish set switched to BTC/ETH/SOL/DOGE. DOGE was not previously in the
spent specialist promotion set. Nested yearly walk-forward on DOGE (same
multi-market harness: expanding folds, 80-bar embargo, next-open, stop-first,
DOGE 12 bps fill assumption + taker fees):

| Year | Trades | Win rate | Mean R |
|---|---:|---:|---:|
| 2022 | 24 | 37.5% | +0.365 |
| 2023 | 29 | 44.8% | +0.120 |
| 2024 | 30 | 53.3% | +0.653 |
| 2025 | 28 | 25.0% | −0.162 |
| 2026 | 22 | 27.3% | −0.193 |

Combined: **133 trades**, 38.3% wins, **+0.173R**, 1.28 PF, 14.95R DD, 60%
positive years → **PASS** absolute gates.

Encoded as `doge-mtf-bos-volume-profit` v1 in `PAPER_MODEL_REGISTRY`
(**paper-only**, live alerts blocked). Note: 2025–2026 folds were negative, so
paper soak is required before any alert discussion. BTC/ETH remain WAIT (prior
rejects). SOL V1 remains the primary soak incumbent.
