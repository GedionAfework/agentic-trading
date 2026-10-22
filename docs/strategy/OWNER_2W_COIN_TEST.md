# Owner goal — test 4 coins + best agent in ≤2 weeks

Written: 2026-10-13  
Owner coins: **BTC, ETH, SOL, DOGE**

## What “best agent” means here

Not “trades every hour and always wins.”

The best agent:

1. Watches only the owner coins.
2. Takes **special** setups only (fail closed → WAIT otherwise).
3. Opens **paper** trades only when a model is validated for that coin.
4. Never invents live profitability or turns on live alerts by default.
5. Reports honest accept/reject per coin.

## What we already know (do not pretend otherwise)

| Coin | Research status | Paper? |
|---|---|---|
| SOL | V1 profit incumbent (+0.215R WF) | Yes — active soak |
| BTC | Failed honest WF / specialists | No — WAIT |
| ETH | Failed honest WF / specialists | No — WAIT |
| DOGE | Nested WF PASS 2026-10-13 (+0.173R, 133 trades) | Yes — paper-only v1; 2025–2026 negative |

Re-searching the **same** BTC/ETH idea space on 2022–2026 to “make them pass” is not allowed.

## 2-week plan

### Days 1–3 — Universe + data
- Core crypto universe = BTC, ETH, SOL, DOGE (BNB out of owner set).
- Backfill DOGE 1h/4h/1d.
- Agent/scanner scope = those four symbols; still fail closed.

### Days 3–7 — Honest coin tests
- **DOGE:** new nested walk-forward (unused coin). Promote to paper only if gates pass.
- **BTC/ETH:** do **not** retune spent families. Either WAIT, or one *new* unused hypothesis (new catalog version) if time allows.
- **SOL:** keep V1 paper soak running (background proof).

### Days 7–14 — Ship shape
- Publish as **paper-only best agent** for the owner coins.
- Live Telegram alerts stay off unless owner signs Gates A–G + explicit soak waiver.
- Marketing: “paper validation / research agent,” not “guaranteed wins.”

## Gates (unchanged honesty)

Crypto promote-to-paper needs roughly: ≥80 WF trades, mean R > 0.05, PF > 1.1, DD ≤ 20R, ≥60% positive periods. SOL challengers must also beat V1 expectancy.

## Success in 2 weeks

Success = a clean agent that correctly trades **only** what passed, and WAITS on the rest — not 80 live paper fills on every coin.
