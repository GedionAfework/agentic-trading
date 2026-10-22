# Soak freeze journal — Step 0

Frozen: 2026-10-08  
Freeze id: `soak-v1-2026-10-08`  
Last commit at freeze write: `937a58117ddbd80abee54d12d006f11fda49e0ac`  
Lock is the **model codes and soak profile**, not a promise that the working tree is clean.

## Profile

| Field | Frozen value | Why |
|---|---|---|
| Symbol | SOL/USDT | Only pair with a surviving after-cost incumbent |
| Entry | 1h | Challenger entry timeframe |
| Bias | 4h | Challenger higher timeframe |
| Objective | `profit` | V1 expectancy (+0.215R) is the thing to prove |
| Active model | `sol-mtf-bos-volume-profit` v1 | Paper incumbent |
| Alternate (not active) | `sol-mtf-bos-volume-scale-out` v2 | Win-rate / scale-out; do not swap in mid-soak without a written reason |
| Specialists | none | `VALIDATED_SPECIALIST_MODELS` is empty |
| Owner scan set | BTC/ETH/SOL/DOGE | Unvalidated → WAIT; DOGE paper model added 2026-10-13 |
| Live alerts | blocked | `paper_only=true`, `live_alerts_allowed=false` |
| Selection data | through 2025-12-31 | Do not retune on that sample |

## Fill / cost assumptions to log against paper fills

Paper engine default (what Step 1 will use):

- fill: next-open
- ambiguity: conservative stop-first
- fee: 10 bps/side (0.001 taker, same as research)
- slippage: 5 bps
- spread: 2 bps
- risk: 0.5% of equity
- max bars in trade: 80 (V1)

Research SOL fill degradation was 8 bps combined. Paper splits slippage/spread (5+2). Log the gap; do not change entries to hide it.

## Runtime freeze

- Scheduled `scanner.scan_all` scans **SOL/USDT 1h** with objective `profit` only.
- A scan with an objective and no symbol list also collapses to that soak scope.
- BTC, ETH, BNB, and FX stay `WAIT` (no validated paper model).
- Paper-eligible ENTER is not publishable.

## Do not do during this freeze

- Search 2022–2026 again
- Add specialist registry rows
- Switch the soak to V2 without updating this journal
- Enable live alerts

Step 1 is running (2026-10-12): Docker, API, Celery worker + beat are up.
Scheduled soak scans hit SOL/USDT 1h with objective `profit`. Candle sync no
longer dies on Yahoo FX errors; ancient open gaps no longer block live
actionability. Step 1 is not *complete* until 20 closed SOL V1 paper trades
exist with fill quality vs research written down.

Step 2 is running on the same live stream (2026-10-12): `soak_step2` tracks the
full sample gates (80 trades, mean R > 0, PF > 1.1, DD ≤ 20R, ≥60% positive months
with ≥4 trades, fill gap < 2 bps). Step 2 is not *complete* until
`ready_for_holdout_review` is true.

Step 3 is wired: `soak_step3` scores only paper trades closed on/after
`2026-10-08` (post-freeze). Historical 2022–2026 is spent for V1. Step 3 stays
`WAIT` until Step 2 passes and the post-freeze holdout clears the same gates
plus a competitive mean-R floor (half of +0.215R).

Step 4 is wired: `soak_step4` confirms paper-only promotion when Step 3 PASSes.
It locks risk from observed DD (never above 0.5%, cuts after rough DD), keeps
live alerts off, and keeps every other pair on WAIT. D-01 policy and D-15 gate
are recorded in OPEN_DECISIONS; D-15 stays “not confirmed” until Step 4 PASSes.

Step 5 is wired: `soak_step5` is the live-alert readiness gate. Default WAIT.
It requires Step 4 PASS plus explicit owner unlock setting
`soak_live_alert_owner_unlock`. Even READY leaves `live_alerts_allowed=false`
and does not enable release alerts. Channel remains Telegram only.

Step 6 (optional challenger) ran once: SOL `sol-mtf-daily4h-v3` (1d+4h)
REJECT for insufficient trades (42 < 80). Does not change this freeze, the
active soak model, or the empty specialist registry.
