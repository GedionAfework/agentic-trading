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
