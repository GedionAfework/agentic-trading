# Strategy Specification v1 — Crypto-first (Wyckoff + HDM + AMT)

**Document status:** DRAFT — pending primary course cites and owner lock  
**Strategy id (proposed):** `wyckoff-hdm`  
**Semantic version:** `1.0.0-draft`  
**Supported asset classes (v1):** `CRYPTO` only for actionable gates  
**First instruments:** `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `SOLUSDT`  
**Primary timeframes:** HTF `1W`/`1M` · Setup `1D`/`4H` · Timing `1H`/`30m`

> Until `resources/incoming/` course files are attached, rules below are **SOURCE-DERIVED (pending primary cite)** from the Implementation Roadmap baseline of your supplied materials. Thresholds marked **EC** are engineering candidates, not course facts.

---

## 1. Intent

Encode the owner's framework as versioned, testable rules so the platform can:

1. Continuously evaluate markets without LLM-per-tick.
2. Emit `WAIT` / `NO_SETUP` as often as actionable entries.
3. Require evidence for every mandatory condition (TRUE/FALSE/UNKNOWN).
4. Never claim guaranteed profitability.

---

## 2. Market context requirements

### 2.1 Required for any actionable crypto decision

| Input | Required | Notes |
|-------|----------|-------|
| OHLCV at HTF + setup TF + timing TF | Yes | Gaps → UNKNOWN → block READY |
| Instrument metadata (tick/step) | Yes | Risk sizing |
| Data freshness | Yes | Stale → fail closed |
| Session / weekend policy flag | Config | SES-001 |

### 2.2 Recommended context (soft unless Spec promotes)

| Input | Use |
|-------|-----|
| Order book imbalance | Context / later features |
| CVD / trade delta | Order-flow features |
| Open interest, funding, liquidations | Crowding / forced flow |
| Spot/perp basis | Premium/discount |
| Macro/news | Optional veto later |

Missing soft context must **not** silently pass a hard gate that requires it.

---

## 3. Multi-timeframe hierarchy

| Role | Timeframes | Responsibility |
|------|------------|----------------|
| HTF | Weekly, Monthly | Wyckoff phase / major structure bias |
| Setup | Daily, 4H | Trend, entry zone, cause/effect |
| Timing | 1H, 30m | BOS confirmation, volume, entry trigger |

**Alignment rule (mandatory):** Timing entry direction must agree with HTF bias. If HTF bias unclear → `WAIT` / `NO_SETUP`.

---

## 4. Hard signal gate (LONG / SHORT / WAIT)

SOURCE-DERIVED checklist. **All mandatory items must be TRUE** for `ENTER_*` / `READY_FOR_REVIEW`. Any FALSE or UNKNOWN → cannot fully qualify.

| Code | Condition | Directionality | Mandatory |
|------|-----------|----------------|-----------|
| `htf_aligned` | HTF bias agrees with trade direction | long/short | Yes |
| `bos_confirmed` | BOS in trade direction on timing/setup TF per STR-002 | long/short | Yes |
| `volume_harmony` | Effort/Result harmony supports direction (VOL-001 family) | long/short | Yes |
| `acc_dist_context` | Accumulation (long) / distribution (short) context present | long/short | Yes — may be ADV until WYK locked |
| `imbalance_favoring` | Market imbalance / auction context favors direction | long/short | Yes — may be ADV until locked |
| else | — | — | → `WAIT` or `NO_SETUP` |

---

## 5. Five-question pre-entry gate

Any **NO** or **UNKNOWN** → `WAIT` (not ENTER).

| # | Question | Rule code | Pass criteria |
|---|----------|-----------|---------------|
| Q1 | Confirmed BOS + volume? | `q_bos_volume` | `bos_confirmed` AND significant volume (VOL-001) |
| Q2 | Harmonious volume? | `q_volume_harmony` | Harmony true for direction |
| Q3 | Smart Money state OK? | `q_smart_money` | SMT-001 definition — **OPEN** |
| Q4 | Structural stop beyond hunt zone? | `q_structural_stop` | Stop placed per STP-001; hunt zone respected |
| Q5 | R:R at least 1:2? | `q_min_rr` | `rr_to_tp1 >= min_rr` (proposed `2.0`) |

---

## 6. Entry paths

### 6.1 Safer entry (preferred)

Sequence (all steps required unless Spec says optional):

1. BOS close/confirm with **significant volume** (VOL-001).
2. Pullback / retest of approved zone.
3. Retest prints **low volume** (VOL-002).
4. Trigger condition for entry (candle/structure — ENT-001 lock).
5. Pass five-question gate + risk gate.

**State while waiting for retest:** `WAIT_FOR_CONFIRMATION` / `watch`.

### 6.2 Aggressive entry

1. Confirmed BOS + significant volume.
2. First confirmation candle (ENT-002).
3. Five-question + risk gates.

Higher aggressiveness → optional stricter RiskPolicy or lower size — **OWNER DECISION**.

---

## 7. Stop / invalidation

| Rule | Statement |
|------|-----------|
| Structural stop | Beyond invalidating structure / hunt zone — not arbitrary round numbers |
| Buffer | `STP-001` (ATR or tick) — OWNER |
| Missing invalidation | Setup incomplete → cannot `READY_FOR_REVIEW` |
| Invalidation event | Opposite structural evidence / stop touch per paper policy → `INVALIDATED` / `EXIT` |

---

## 8. Targets and exits

| Mode | Working policy | Status |
|------|----------------|--------|
| Staged TP | TP1 / TP2 / TP3 | TP-001 OPEN |
| Structure exit | Opposite MSB / climax / high-volume invalidation | Needs defs |
| Management actions | `TAKE_PARTIAL_PROFIT`, `HOLD`, `REDUCE`, `EXIT` | Product actions |

Until TP-001 locks, backtests must declare assumption set in run metadata.

---

## 9. Decision / setup states (v1 mapping)

| Internal setup state | Typical decision action |
|----------------------|-------------------------|
| no candidate | `NO_SETUP` |
| candidate / watch | `WATCH` |
| waiting retest/confirm | `WAIT_FOR_CONFIRMATION` |
| rules+risk pass | `ENTER_LONG` / `ENTER_SHORT` (user-facing) / `READY_FOR_REVIEW` |
| stop/structure break | `INVALIDATED` / `EXIT` |
| time/candle expiry | `EXPIRED` |

---

## 10. Risk coupling

Strategy Spec does **not** embed account risk %. It references a `risk_policy_id`.

Minimum strategy-level constraints:

- `min_rr` (proposed 2.0 from Q5)
- Invalidation required
- Freshness required
- Mandatory UNKNOWN handling

Portfolio limits (max concurrent, daily loss, correlation) live in RiskPolicy.

---

## 11. What is deterministic vs advisory in v1

| Concept | v1 stance |
|---------|-----------|
| Swings, BOS (once STR-* locked), volume ratios, R:R, freshness | **Deterministic** |
| Safer/aggressive sequences once ENT-* locked | **Deterministic** |
| Wyckoff phase labels (Spring/UTAD/LPS) until WYK-001 locks | **Advisory** (cannot alone authorize ENTER) |
| LLM chart narrative | **Advisory** |
| ML decision score (Phase 11+) | **Ranking only**; cannot bypass hard gates |

---

## 12. Acceptance for this Spec document

Phase 0 Spec gate is met when:

- [ ] Primary course files inventoried and cited on each mandatory rule
- [ ] VOL-001, VOL-002, STR-002, SMT-001, STP-001, TP-001 resolved or explicitly `advisory_only` / deferred
- [ ] Owner accepts crypto-first instrument list
- [ ] Forex explicitly out of actionable scope
- [ ] At least 10 labeled examples planned (see LABELED_EXAMPLE_PLAN.md)
- [ ] Owner sign-off below

### Owner sign-off

| Field | Value |
|-------|-------|
| Name | |
| Date | |
| Spec version approved | |
| Notes | |

---

## 13. Change control

Edits after sign-off create `1.0.1-draft` / `1.1.0-draft` etc. Published engine versions must reference an approved Spec hash/version. Historic setups keep the `strategy_version_id` they were evaluated with — never mutate in place.
