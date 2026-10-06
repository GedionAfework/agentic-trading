# Conflicts and gaps

## 1. Risk policy conflicts

| ID | Conflict | Resolution path | Status |
|----|----------|-----------------|--------|
| RISK-C01 | Personal max-risk notes vs course “smaller risk after consistency” guidance | Store as **versioned RiskPolicy**; never hard-code a single % in strategy code | **OWNER DECISION** open |
| RISK-C02 | Paper vs future live limits may differ | Separate `paper` and `live_alert` policy profiles | Proposed |
| RISK-C03 | Weekend crypto avoidance (if personal rule) vs 24/7 crypto markets | Configurable strategy/risk policy flag, not buried in feature code | **OWNER DECISION** open |

## 2. Forex gaps (explicit)

| ID | Gap | Impact | Status |
|----|-----|--------|--------|
| FX-G01 | Course material stronger for crypto than Forex | Do not claim FX parity in V1 | **GAP** |
| FX-G02 | No approved FX volume proxy for “volume harmony” | Harmony/divergence gates cannot be deterministic on FX yet | **GAP** |
| FX-G03 | Exact first FX pairs not specified by sources | Choose after provider + adaptation rules | **OWNER DECISION** |
| FX-G04 | Spread / session / economic-event rules for FX incomplete | Need calendar + blackout policy | Open |
| FX-G05 | Labeled FX example trades missing | Block FX strategy golden tests | **GAP** |

**V1 stance:** Crypto-first (BTC, ETH, BNB, SOL). Forex adapters may exist for data, but **no FX READY_FOR_REVIEW / ENTER_*** until FX-G02–G05 are addressed.

## 3. Definition gaps (crypto)

| ID | Gap | Blocks |
|----|-----|--------|
| DEF-G01 | Numeric “significant volume” | Safer/aggressive entry hard gates |
| DEF-G02 | Numeric “low-volume retest” | Safer entry READY state |
| DEF-G03 | BOS close vs wick + confirmation latency | Structure features |
| DEF-G04 | Which Wyckoff events are code vs advisory | Feature engine scope |
| DEF-G05 | Smart Money state operationalization | Five-question checklist Q3 |
| DEF-G06 | Exact TP staging policy | Exit / paper simulation |

## 4. Data / licensing gaps

| ID | Gap | Notes |
|----|-----|-------|
| DATA-G01 | Historical crypto OHLCV + optional derivatives | Required for backtest |
| DATA-G02 | Screenshot ZIP for vision benchmark | Prefer originals |
| DATA-G03 | Past trades including losers and WAIT | Required for honest labels |
