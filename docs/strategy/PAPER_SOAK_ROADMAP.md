# Roadmap — prove the SOL paper models, do not retune them

This is how to *perfect* the current system without inventing an edge.
The only incumbents are `SOL_MTF_CHALLENGER_V1` (expectancy) and
`SOL_MTF_CHALLENGER_V2_SCALE_OUT` (higher win rate). Both are paper-only.
BTC, ETH, BNB, FX, and all pair specialists stay `WAIT`. Live alerts stay
blocked until a later, unused period clears the gates below.

Do **not** search 2022–2026 again. That sample is spent.

## Current bar

| Model | Role | Walk-forward | Status |
|---|---|---|---|
| SOL V1 | Profit / expectancy | 164 trades, 40.9% wins, **+0.215R** | Paper only |
| SOL V2 | Win-rate / scale-out | 175 trades, 58.9% wins, **+0.059R**; 26-trade 2026 holdout | Paper only |
| Pair specialists | BTC, ETH, BNB, SOL, 8 FX | None promoted | Registry empty |

## Hard rules for every step

- SOL/USDT, 4h bias + 1h entry, next-open fills, stop-first, configured costs.
- One position per symbol, existing portfolio gates, no live execution.
- No new parameters, filters, or families on data already used for selection.
- A later research version may only replace V1/V2 if it **beats them on unused bars**.

## Step 0 — Freeze the incumbents

Status: **done** (2026-10-08). Journal: [SOAK_FREEZE.md](./SOAK_FREEZE.md).

1. Confirm runtime routing: SOL paper models only; everything else `WAIT`.
2. Confirm `VALIDATED_SPECIALIST_MODELS` is empty and `live_alerts_allowed` is false.
3. Pick the paper profile and do not switch mid-soak without a written reason:
   - `profit` → V1 **(active soak)**
   - `win_rate` → V2 scale-out (frozen alternate)
4. Record the git SHA, model codes, fill model, and cost assumptions in the journal.

**Done when:** scanner cannot publish live alerts, and a SOL `ENTER` is paper-eligible only.

## Step 1 — Turn paper trading on and measure fills

Status: **running** (2026-10-12). Infra + API + Celery worker/beat are up.
SOL/USDT 1h is fresh and actionable; soak scans resolve
`sol-mtf-bos-volume-profit` v1. Waiting on live time for ENTER signals and
**20 closed** SOL V1 paper trades (`GET /paper/account` → `soak_step1`).

1. Enable the scanner for SOL 1h with objective `profit` (scheduled `scanner.scan_all`).
2. Paper-eligible ENTER auto-opens a paper trade. V1 is binary 3R, 80-bar timeout, no scale-out.
3. For every fill/close, journal: signal time, next-open raw vs fill, assumed vs research bps, stop/target/timeout, R-multiple, blockers.
4. Compare paper mean R, win rate, and extra fill bps to V1 research after **20 closed trades** (`GET /paper/account` → `soak_step1`).

**Kill / continue**

- Continue if after-cost paper mean R > 0 and costs are not materially worse than research.
- Pause and inspect if paper mean R ≤ 0, or if fills are systematically worse than the cost model.
- Do not “fix” this by tightening rules on old candles.

**Done when:** 20 paper trades exist with fill quality vs backtest written down.

## Step 2 — Soak until the sample is large enough

Status: **running** (2026-10-12). Progress: `GET /paper/account` → `soak_step2`.
Same live SOL V1 stream as Step 1 — Step 2 just needs a larger sample (80
closed trades) plus expectancy / PF / DD / monthly / fill-gap gates. Still at
0 closed soak trades until the scanner prints ENTERs.

Keep the frozen V1 model running on **new** candles only.

Minimum evidence before any promotion talk:

| Gate | Minimum |
|---|---|
| New closed paper trades | 80 (V1 active soak) |
| After-cost mean R | > 0 |
| Profit factor | > 1.1 |
| Max drawdown | ≤ 20R |
| Positive calendar months | ≥ 60% of months with at least 4 trades |
| Fill gap vs research | Average extra cost < 2 bps beyond the assumed model |

`soak_step2.all_gates_passed` / `ready_for_holdout_review` is true only when every
gate passes. `blocking_gates` names whatever is still missing.

Calendar time is whatever it takes to print those trades. Do not speed this up by adding symbols.

**Done when:** the table is filled from paper, not from a new backtest of 2022–2026.

## Step 3 — Holdout review (unused period only)

Status: **wired** (2026-10-08). Progress: `GET /paper/account` → `soak_step3`
(or `uv run python scripts/_soak_holdout_review.py`).

Because SOL V1 already used 2022–2026 in walk-forward folds, the only honest
unused window is **closed SOL paper trades on/after the soak freeze
(`2026-10-08`)**. Do not recycle historical candles as a new holdout.

1. Require Step 2 complete first (`gates.step2_complete`).
2. Score the **frozen** V1 config only on that post-freeze paper window.
3. Apply the same gates as Step 2, plus:
   - V1 mean R ≥ 50% of research (+0.1075R floor vs +0.215R). Positive but
     tiny expectancy is not “competitive.”
   - Decision is `PASS` or `WAIT` (`approved_for_paper_promotion`).

**Fail:** stop. Keep `WAIT` for live. Either soak longer or, only then, open a **new research version** with a genuinely different idea and a fresh embargoed walk-forward.

**Pass:** go to Step 4.

## Step 4 — Paper promotion (still not live)

Status: **wired** (2026-10-08). Progress: `GET /paper/account` → `soak_step4`.
Stays `WAIT` until Step 3 PASSes.

If Step 3 passes:

1. Confirm surviving SOL model remains `validated_for_paper`, `paper_only=true`, `live_alerts_allowed=false`.
2. Lock D-01 risk from observed holdout drawdown: base 0.5%, cut to 0.35% if DD>10R, 0.25% if DD>15R. Never raise size because the soak looked good (`locked_risk_pct`).
3. Keep BTC/ETH/BNB/FX on `WAIT`. Specialists stay empty. Do not roll out to other pairs.

**Done when:** `soak_step4.decision=PASS` and OPEN_DECISIONS D-15 can flip to soak-confirmed. Live alerts remain blocked.

## Step 5 — Live alert decision (separate, later)

Status: **wired** (2026-10-08). Progress: `GET /paper/account` → `soak_step5`.
Default decision is **WAIT**. This step never flips `live_alerts_enabled`.

Only after Step 4 PASS, and only with an explicit owner unlock setting
(`soak_live_alert_owner_unlock.enabled=true`):

1. Lock D-11 (alerts) and keep D-01 size at `locked_risk_pct` (≤ 0.5%).
2. First channel is Telegram only (D-12).
3. Portfolio gates and daily loss stop remain required.
4. Kill rule: if any live week max DD exceeds paper holdout DD by >50%, disable
   live alerts and revert to paper-only WAIT.
5. Even when `decision=READY`, `live_alerts_allowed` stays false here. An owner
   must still unlock through the release checklist / `enable_live_alerts`.

This step is not scheduled. It is a gate, not a date.

## Step 6 — Optional new research (only if soak fails or you want a challenger)

Status: **ran** (2026-10-08). Hypothesis: [STEP6_HYPOTHESIS.md](./STEP6_HYPOTHESIS.md).
Catalog `sol-mtf-daily4h-v3` (1d bias + 4h entry). Result: **REJECT** —
+0.475R mean beat V1, but only 42 walk-forward trades (need ≥80). Spec stays
research-only; registry unchanged; soak stays on V1.

Allowed only as a **new catalog version**, never as silent edits to V1/V2:

1. Write the hypothesis first (example: unused timeframe, unused exit, unused data). Do not rescan the specialist families we already rejected.
2. Nested walk-forward, 80-bar embargo, pair-specific costs, per-symbol promotion.
3. Challenger must beat the incumbent **and** pass the absolute gates on unseen data.
4. Record accept/reject in `BACKTEST_FINDINGS.md`. Failed models never enter the registry.

BTC/ETH/BNB/FX stay research-only until a challenger passes this step on that symbol alone.
A later Step 6 version needs a different unused idea (or more calendar data),
not a looser trade-count gate on this catalog.

## What this roadmap is not

- A plan to make all pairs trade.
- A plan to raise win rate to 80% by adding filters.
- A promise of live profitability.

The system is perfected when the frozen SOL models keep working on **new** trades, or when we honestly keep WAIT. Either outcome is success. Forcing trades is not.
