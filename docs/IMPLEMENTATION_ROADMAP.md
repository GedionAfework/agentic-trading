# Private Self-Hosted AI Trading Copilot — Unified Implementation Roadmap

**Status:** Active build plan — **Phase 7 landing**  
**Sources:** SRS v2.0, SDS v2.0, Architecture Design v2.0, Database Design v2.0, Complete Implementation Roadmap v1.0  
**Safety boundary:** No autonomous live-money execution in baseline  
**Last updated:** October 2026  
**Phase 0 workspace:** [`docs/strategy/`](./strategy/README.md)  
**Phase 1:** uv workspace, FastAPI `/health`, Compose stack under `infra/docker/`  
**Phase 2:** Alembic identity/ops schema, `/v1/auth/*`, owner seed (`pta-seed-owner`)  
**Phase 3:** `AIGateway` (Ollama), model/prompt registry, `/v1/ai/health` + smoke endpoints  
**Phase 4:** Knowledge upload/chunk/embed/approve + `/v1/knowledge/ask` with citations  
**Phase 5:** Market catalog + Binance spot candles + freshness/health APIs  
**Phase 6:** Deterministic features (ATR/swings/BOS/volume) with UNKNOWN fail-closed  
**Phase 7:** Strategy DSL + wyckoff-hdm gates + publish/evaluate APIs

---

## 0. How we use this document

This is the single build sequence we follow. Order matters.

1. Formalize strategy definitions before coding trade decisions.
2. Build deterministic market → feature → strategy → risk path before AI explanations.
3. Backtest and paper-trade before live recommendation alerts.
4. Keep live broker execution out of scope until a separately designed bounded context exists.

Every phase has: purpose, work items, deliverables, acceptance gate, and dependencies.

---

## 1. Product understanding (source of truth)

### 1.1 What we are building

A **private, self-hosted AI trading copilot** for a single owner/trader that:

- Ingests the owner's trading courses, strategies, screenshots, and guides into a private RAG corpus.
- Continuously monitors configured Crypto (first) and Forex (after adaptation rules) markets.
- Detects candidate setups using **deterministic** strategy and risk rules.
- Explains setups via self-hosted LLM/VLM with citations — never inventing unverifiable numbers.
- Delivers alerts and Q&A through **Expo/React Native** and **Telegram**.
- Journals outcomes for analytics, backtesting, and (later) ML decision scoring.
- Remains **decision support**, not autonomous execution and not a profitability guarantee.

### 1.2 Core architectural principle

```
AI (probabilistic)          Deterministic authority
─────────────────           ──────────────────────
retrieve / summarize        indicators / features
classify / explain          strategy rule predicates
propose interpretations     risk / R:R / sizing math
screenshot extraction       freshness / quality gates
journal narration           signal state machine
                            notification dedupe
```

**Hard rule:** LLM/VLM cannot override strategy or risk gates. Model-generated prices/risk numbers are informational until recomputed by deterministic code.

### 1.3 Eight logical agents (+ Decision layer later)

| ID | Agent | Role |
|----|--------|------|
| AG-01 | Orchestrator | Intent → workflow; tool routing; budgets |
| AG-02 | Knowledge | Private RAG + citations; insufficient-evidence honesty |
| AG-03 | Vision | Chart screenshot extraction; no fabricated precision |
| AG-04 | Market Data | Normalized candles/snapshots only |
| AG-05 | Strategy | Maps facts to versioned rule evaluation |
| AG-06 | Risk | R:R, invalidation, freshness, policy veto |
| AG-07 | Signal | Publish policy + lifecycle states |
| AG-08 | Journal/Analytics | Metrics narrative over computed stats |
| AG-09 | Decision (Phase 11+) | Optional ML score + calibrated confidence; still vetoable by risk/rules |

Agents are **logical roles** around shared model servers — not eight separate 27B deployments.

### 1.4 Baseline non-goals

- No live order placement / broker execution credentials in baseline.
- No guaranteed buy/sell predictions or profitability claims.
- No HFT / ultra-low-latency trading.
- No training a foundation model from scratch.
- No multi-tenant public SaaS / signal marketplace in baseline.
- No mandatory public LLM/embedding APIs in production.

### 1.5 Trading framework we encode (from strategy materials)

Source-derived concepts to preserve (not generic trading advice):

- **Framework:** Wyckoff + Harmonic Divergence Matrix + Auction Market Theory.
- **Effort vs Result:** Volume = Effort; Price = Result; harmony vs divergence.
- **MTF hierarchy:** Weekly/Monthly HTF → Daily/4H setup → 1H/30m timing.
- **Hard gate:** LONG/SHORT needs BOS + volume harmony + accumulation/distribution context + imbalance in trade direction + HTF alignment; else WAIT.
- **Five-question pre-entry:** Confirmed BOS+volume; harmonious volume; Smart Money state; structural stop beyond hunt zone; R:R ≥ 1:2. Any NO → WAIT.
- **Entries:** Safer retest path vs aggressive first-confirmation path.
- **Exits:** Structure-based invalidation; staged TP1/TP2/TP3; climax/reversal exits.
- **First crypto symbols:** BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT.
- **Forex:** Explicit gap — needs adaptation rules, volume proxies, and labeled examples before claiming parity.

Ambiguous English terms (`significant volume`, `low-volume retest`, etc.) become **versioned measurable parameters** after validation — never silent invention.

### 1.6 Signal / decision vocabulary (unified)

**Setup lifecycle (SRS/DB):**  
`candidate → watch → ready_for_review → invalidated | expired | closed`

**User-facing decision actions (roadmap, when Decision Agent exists):**  
`NO_SETUP | WATCH | WAIT_FOR_CONFIRMATION | ENTER_LONG | ENTER_SHORT | HOLD | REDUCE | TAKE_PARTIAL_PROFIT | EXIT | INVALIDATED | EXPIRED`

Until Phase 12, the product surface may expose the simpler setup states. Decision actions layer on top without mutating historical setup evidence.

### 1.7 Stack (locked for V1)

| Layer | Choice |
|--------|--------|
| Language / tooling | Python 3.12, `uv`, lockfile |
| API | FastAPI + Pydantic v2 |
| ORM / migrations | SQLAlchemy 2 async + Alembic |
| DB | PostgreSQL 16 + pgvector |
| Cache / broker | Redis |
| Workers | Celery (or Arq if we later simplify) |
| Inference (dev → prod) | Ollama first; vLLM optional later |
| Models | Qwen-class text/VLM + Qwen embedding; LightGBM/XGBoost for Decision ML |
| Object storage | MinIO / S3-compatible |
| Mobile | Expo + React Native + TypeScript |
| Telegram | aiogram + webhook |
| Proxy / deploy | Nginx + Docker Compose on Ubuntu; K8s later if needed |
| Observability | Prometheus + Grafana + structured logs / OTel |

### 1.8 Repo shape (target)

```
agentic-trading/
├── pyproject.toml / uv.lock / .python-version
├── apps/          # api, worker, telegram
├── packages/      # core, db, market_data, features, strategies, risk,
│                  # knowledge, ai_gateway, agents, decision, backtest,
│                  # paper_trade, journal, notifications
├── mobile/
├── infra/         # docker, nginx, compose, monitoring
├── migrations/
├── data_contracts/
├── docs/          # this roadmap + specs notes
├── notebooks/     # research only — never production source of truth
└── tests/         # unit, integration, contract, strategy, decision, rag, vision, e2e
```

Architecture preference: **modular monolith first** with clean package boundaries.

---

## 2. Build blocks overview

| Block | Phases | Outcome |
|-------|--------|---------|
| A — Foundation | 0–3 | Spec, repo, DB/auth, private AI gateway |
| B — Core trading brain | 4–8 | RAG, market data, features, strategy, risk |
| C — Validation intelligence | 9–12 | Backtest, datasets, Decision ML, Decision Agent |
| D — Delivery surfaces | 13–16 | Vision, scanner, Telegram, paper trading |
| E — Product release | 17–20 | Mobile, analytics, hardening, live *alerts* only |

Indicative solo pace: **months, not weeks**. Largest uncertainty is strategy formalization, data licensing, labeled examples, and out-of-sample Decision validation — not FastAPI scaffolding.

---

## 3. Detailed phases

### Phase 0 — Resource audit and Strategy Specification v1

**Purpose:** Stop coding trade logic against vague English.

**Work**
- Inventory all course/DOCX/PDF/screenshot/ZIP materials; assign authority tiers (Tier-1 rules → Tier-5 public research).
- Build concept glossary (BOS, MSB, Spring, UTAD, LPS, FVG, harmony/divergence, etc.).
- Conflict log (personal risk notes vs course risk guidance).
- Forex gaps list (volume proxy, pairs, session rules).
- Measurable-definition backlog for every mandatory term.
- Curate screenshot pages: keep / discard / duplicate flags.
- Choose first crypto symbols and defer FX pairs until provider + adaptation rules exist.
- Draft Strategy Specification v1 with source references per rule.

**Deliverables**
- `docs/strategy/STRATEGY_SPEC_v1.md`
- Source inventory + authority matrix
- Glossary + conflicts + Forex gaps
- Labeled-example plan

**Acceptance gate**  
No coding of trade decisions until every mandatory entry/exit term has either a deterministic definition or explicit `AI-only/advisory` status.

**Depends on:** source materials available.

---

### Phase 1 — Repository, uv, and developer tooling

**Purpose:** Reproducible clone → run path.

**Work**
- `uv` workspace, package layout, `.python-version` pin.
- Docker Compose: Postgres+pgvector, Redis, MinIO.
- Config via pydantic-settings; `.env.example` (no secrets committed).
- Structured logging with `correlation_id`.
- Ruff, mypy, pytest, pre-commit, GitHub Actions skeleton.
- API health endpoint.

**Deliverables**
- Green CI on empty/skeleton tests
- Compose stack boots locally (Windows + Docker Desktop / WSL2)

**Acceptance gate**  
Fresh machine: clone → `uv sync` → start deps → health check → tests pass with no undocumented steps.

**Depends on:** Phase 0 started (can parallelize tooling while finishing Strategy Spec).

---

### Phase 2 — Database and identity foundation

**Purpose:** Source-of-truth schema + secure owner access.

**Work**
- Alembic + SQLAlchemy models for domains:
  - identity: users, sessions, mfa_methods, telegram_accounts, user_roles
  - ops: audit_events, outbox_events, idempotency_keys, system_settings
  - stubs for knowledge/strategy/market/trading as empty shells or minimal tables
- Auth: Argon2id, short-lived JWT access + opaque hashed refresh, revoke, optional TOTP.
- RBAC capability checks server-side.
- Telegram link challenge (one-time) — wiring can complete in Phase 15.
- Object-storage metadata pattern (object_key, sha256, mime).

**Deliverables**
- Initial migrations
- `POST /v1/auth/login|refresh|logout`, session list/revoke
- Audit on auth security events

**Acceptance gate**  
Invalid credentials do not leak user existence; revoked refresh cannot call protected APIs; migrations apply cleanly.

**Depends on:** Phase 1.

---

### Phase 3 — Private AI Gateway (Ollama)

**Purpose:** Backend-only inference with structured outputs.

**Work**
- Install Ollama; pull baseline text/multimodal + embedding models (treat exact versions as config).
- `ai_gateway` client: timeouts, retries, circuit breaker, token budgets.
- Prompt registry (`prompt_versions`) + model registry rows.
- Structured JSON output validation (Pydantic); one repair attempt then fail closed.
- Redaction filters: never send secrets to prompts/logs.

**Deliverables**
- Private inference reachable only from API/workers
- Smoke: generate structured stub response + embed text

**Acceptance gate**  
Mobile/Telegram cannot reach Ollama; structured validation + failure handling tested; inference ports not public.

**Depends on:** Phase 2.

---

### Phase 4 — Knowledge / RAG pipeline

**Purpose:** Approved private corpus with citations.

**Work**
- Upload → quarantine → type/size validation → parse (PDF/DOCX/MD/TXT) → normalize → chunk (heading-aware, 400–900 tokens, 10–20% overlap) → embed → DRAFT.
- Owner approval required before production retrieval (BR-007).
- Hybrid retrieval: pgvector + optional FTS; metadata filters (strategy, asset class, timeframe, status).
- Authority tiers; Tier-5 cannot override Tier-1.
- Golden Q&A set + unsupported-query set + prompt-injection corpus.
- Persist `retrieval_events` and `response_citations`.

**Deliverables**
- Knowledge APIs: upload, approve, list, Ask (via orchestrator stub)
- Evaluation report for RAG Gate C

**Acceptance gate**  
Known questions cite expected sources; unsupported answers say insufficient evidence; injection text in PDFs cannot alter tool policy.

**Depends on:** Phases 2–3; curated materials from Phase 0.

---

### Phase 5 — Market data core

**Purpose:** Normalized, freshness-aware market truth.

**Work**
- Provider protocol: `list_instruments`, `fetch_candles`, subscribe/poll, health.
- First crypto adapter (exchange REST/WS as available) for BTC/ETH/BNB/SOL.
- Instrument catalog, provider_symbol maps, candle idempotent upsert.
- Quality: duplicates, gaps, out-of-order, freshness timestamps.
- Session calendar helpers (crypto 24/7; Forex session scaffolding for later).
- Rate-limit/backoff; connector degraded mode.
- Optional: derivatives context tables stubbed (funding/OI) for later Decision features.

**Deliverables**
- Normalized `Candle` / `MarketSnapshot` contracts
- Health view: last candle age per symbol/timeframe

**Acceptance gate**  
Stale/gapped data fail closed for actionable signals; strategy code never sees provider-specific JSON.

**Depends on:** Phase 2; provider credentials in secret store.

---

### Phase 6 — Deterministic Feature Engine

**Purpose:** Pure, versioned, timestamp-safe features.

**Work**
- Feature registry: lookback, types, version, dependencies.
- Implement: ATR/range, swings, BOS/MSB (per Strategy Spec defs), volume ratios, session features.
- Add Wyckoff/liquidity/FVG primitives only when Spec marks them deterministic.
- No network/DB writes inside feature functions; cache keys include feature version.
- Golden fixtures from labeled examples.

**Deliverables**
- `packages/features` with unit + golden tests
- Feature snapshots optional for evidence

**Acceptance gate**  
Every live feature has unit tests and no look-ahead; missing inputs yield UNKNOWN, not pass.

**Depends on:** Phases 0 and 5.

---

### Phase 7 — Strategy Engine v1

**Purpose:** Versioned DSL rules → explainable assessment.

**Work**
- Tables: strategies, strategy_versions, strategy_rules, strategy_scopes, strategy_test_cases.
- Constrained rule DSL (comparison/composite/sequence); TRUE/FALSE/UNKNOWN.
- Encode LONG/SHORT/WAIT gates + five-question checklist from Spec v1.
- Safer vs aggressive entry paths; structural stop; staged targets as Spec allows.
- Publish creates immutable version; historic setups keep `strategy_version_id`.
- Dry-run against historical window without notifications.
- Score model optional; required FALSE/UNKNOWN always blocks READY.

**Deliverables**
- `StrategyAssessment` / evaluation report
- Publish + fixture APIs
- Golden strategy tests (AT-011..013 class)

**Acceptance gate**  
Golden examples match expected condition matrix; mandatory failure never reaches `ready_for_review`.

**Depends on:** Phases 0, 6.

---

### Phase 8 — Risk Engine

**Purpose:** Independent veto layer.

**Work**
- Versioned `RiskPolicy` (max risk %, min R:R, exposure, event blackouts, weekend policy, etc.).
- Deterministic R:R, invalidation required, freshness gate, optional paper sizing.
- Crypto tick/step/min-notional; FX pip/lot calculator scaffolding.
- Hard blockers vs warnings separation.
- Vocabulary policy: no guaranteed-profit language in templates.

**Deliverables**
- `RiskAssessment` persisted 1:1 with setup
- Hand-verified unit fixtures

**Acceptance gate**  
Invalid entry=stop rejected safely; below min R:R blocks publish; calculations never place live orders.

**Depends on:** Phase 7.

---

### Phase 9 — Historical data and backtesting

**Purpose:** Shared strategy core for live and historical replay.

**Work**
- Acquire licensed/API historical OHLCV (+ spread where possible).
- Event-driven replay; fees/spread/slippage; no look-ahead.
- Pin strategy version + dataset fingerprint + engine version + resolution policy.
- Metrics: trade count, win rate, expectancy in R, drawdown proxy, slices by symbol/TF/session.
- Separate backtest vs paper vs manual outcome labels (BR-008).

**Deliverables**
- Backtest job APIs + report artifacts
- Regression suite on frozen dataset

**Acceptance gate**  
Reproducible metrics within tolerance; audited examples show no look-ahead; same evaluator as live.

**Depends on:** Phases 5–8.

---

### Phase 10 — Training dataset builder

**Purpose:** Leakage-safe tabular rows for Decision ML.

**Work**
- Label engine shared with backtest (entry assumptions, costs, horizons, outcomes).
- Time-based train/val/test splits; walk-forward folds.
- Feature lineage + data-quality report per dataset version.
- Include WAIT/NO_SETUP and losers — not only winners.

**Deliverables**
- Versioned dataset in object storage + DB registry

**Acceptance gate**  
Every row traces to raw timestamps, strategy version, and label policy.

**Depends on:** Phase 9.

---

### Phase 11 — Decision Model v1 (LightGBM/XGBoost)

**Purpose:** Statistical ranking — not LLM math.

**Work**
- Train baseline + challenger; tune only on validation; calibrate or use qualitative bands.
- Model registry: artifact, metrics, feature schema version, training window.
- Abstention thresholds; feature importance export.
- Shadow mode option before champion promotion.

**Deliverables**
- `DecisionModel` predict service behind hard/risk gates

**Acceptance gate**  
Out-of-sample metrics documented; model cannot bypass rules/risk; LLM never invents probability %.

**Depends on:** Phase 10.

---

### Phase 12 — Decision Agent and explanation

**Purpose:** Final recommendation contract.

**Pipeline**
1. MarketContext  
2. Features + StrategyAssessment  
3. Hard no-trade gates  
4. ML score (optional)  
5. Risk veto  
6. Calibrated confidence / band  
7. LLM explanation grounded in computed values + RAG citations  
8. Persist decision snapshot → outbox

**Deliverables**
- Decision record schema (ENTER/WAIT/HOLD/EXIT family)
- Orchestrator workflow wiring AG-01…AG-09

**Acceptance gate**  
All numeric fields from deterministic/statistical services; explanation cites evidence; WAIT/NO_SETUP first-class.

**Depends on:** Phases 4, 7, 8, 11.

---

### Phase 13 — Vision / screenshot analysis

**Purpose:** Charts as supporting evidence, not sole truth.

**Work**
- Upload validation; store in object storage; retention policy.
- VLM structured extraction → symbol/TF confidence → market verification → strategy/risk/decision path.
- Benchmark corpus (200–500 labeled charts); compare multimodal vs dedicated VLM before extra GPU cost.
- User correction of misidentified symbol/TF recorded.

**Deliverables**
- Screenshot analysis job + APIs
- Vision evaluation report (Gate D)

**Acceptance gate**  
Unreadable prices not fabricated; vision never alone authorizes a trade; low confidence forces clarification.

**Depends on:** Phases 3, 5, 7, 8 (Decision optional but preferred).

---

### Phase 14 — Market scanner and background jobs

**Purpose:** Continuous monitoring without LLM-per-tick.

**Work**
- On candle close: normalize → freshness → features → cheap prefilter → strategy → risk → signal/decision → outbox.
- Celery queues: market, AI, notifications, backtests; Redis locks; idempotent consumers; dead letters.
- Kill switches: scanner_enabled, notifications_enabled (independent).
- Dedupe keys: strategy_version + instrument + timeframe + setup anchor + signal type.
- Target: publishable alert <30s after closed candle under healthy conditions (NFR).

**Deliverables**
- 24/7 candidate scanner for approved symbols/TFs
- Ops visibility: queue depth, last success, degraded providers

**Acceptance gate**  
Duplicate candles/jobs do not duplicate alerts; restart recovery safe; stale data produces zero actionable publishes.

**Depends on:** Phases 5–8 (12 recommended before user-facing alerts).

---

### Phase 15 — Telegram bot

**Purpose:** Linked-owner copilot channel.

**Work**
- Webhook + secret validation; link challenge from Phase 2.
- Commands: `/setups`, `/markets`, `/strategies`, `/journal`, `/performance`, `/settings`.
- Free-text → Orchestrator; screenshot upload → vision workflow.
- Alert templates per Appendix D of SRS; buttons: View / Why? / Dismiss / Record decision.
- Unlinked chats: no private data.

**Deliverables**
- Production Telegram webhook path
- Delivery attempts + retry/429 handling

**Acceptance gate**  
Alert numbers match stored Decision/setup; unauthorized chat gets no strategy content.

**Depends on:** Phases 2, 12–14.

---

### Phase 16 — Paper trading

**Purpose:** Forward validation without live money.

**Work**
- Paper accounts, trades, events; fill model assumptions stored.
- Same-candle ambiguity policy (conservative, explicit).
- Monitor stop/targets/invalidation/timeout; realized R; auto-journal.
- Soak period agreed before live alerts (Gate F).

**Deliverables**
- Paper lifecycle from READY → open → close → journal

**Acceptance gate**  
Soak completes without state/notification integrity defects; PAPER clearly labeled.

**Depends on:** Phases 8, 14.

---

### Phase 17 — Mobile app (Expo)

**Purpose:** Primary rich client.

**Screens (per SRS Appendix A)**  
Login/MFA, Dashboard, Setup list/detail, Ask AI, Screenshot analysis, Knowledge library, Strategy editor (or read-only first), Backtests, Paper portfolio, Journal, Analytics, Notifications, Security sessions, System health (admin).

**Work**
- SecureStore tokens; HTTPS only; no provider/model secrets in app.
- Push notifications with deep links; lock-screen payloads concise.
- React Query (or team equivalent) for data; WebSocket optional for live setup updates.

**Deliverables**
- iOS/Android builds against staging then production API

**Acceptance gate**  
Critical flows on physical devices; push + deep link; auth revoke works.

**Depends on:** API surfaces from Phases 2–16 (can start UI against mocks earlier).

---

### Phase 18 — Analytics and continuous learning

**Purpose:** Improve without inventing statistics.

**Work**
- Performance snapshots by strategy/symbol/TF/session; sample-size warnings.
- Similar historical setups; override/feedback review queue.
- Calibration/drift monitoring; challenger model governance.
- Retrain only with explicit evaluation/approval — never P&L panic alone.

**Deliverables**
- Analytics APIs + Journal Agent grounded in SQL aggregates

**Acceptance gate**  
LLM narrates computed metrics only; backtest/paper/manual cohorts never silently merged.

**Depends on:** Phases 9, 16.

---

### Phase 19 — Security, observability, production hardening

**Purpose:** Release Gates A + G.

**Work**
- Nginx/TLS; firewall; private bind for Postgres/Redis/Ollama/MinIO.
- Encrypted backups; restore drill (RPO ≤24h, RTO ≤4h baseline).
- Prometheus/Grafana: API, GPU, freshness, queues, notifications, business setup rates.
- Rate limits, upload abuse controls, secret scan in CI.
- Runbooks: stale feed, GPU down, Telegram 429, DB disk, credential leak, bad strategy version.
- STRIDE controls verified (Architecture Appendix D).

**Deliverables**
- Production readiness report
- Documented runbooks under `docs/ops/`

**Acceptance gate**  
External exposure scan clean; restore + kill-switch tests pass; no critical/high auth/secret findings.

**Depends on:** running system from prior phases.

---

### Phase 20 — Live recommendation release (alerts only)

**Purpose:** Controlled production alerts — still no broker execution.

**Work**
- Enable alerts only after Gates A–G + paper soak.
- Start narrow: approved symbols, conservative notification scope, quiet hours.
- Sign release checklist (SRS Definition of Done + Roadmap §31).
- Explicitly keep execution service undeployed / credentials absent (FR-SIG-008, BR-005).

**Deliverables**
- Production decision/setup alerts for approved markets
- Waiver log for any deferred Must requirements

**Acceptance gate**  
Release checklist signed; automated broker execution remains disabled.

**Depends on:** Phases 16–19.

---

## 4. Cross-cutting work (every phase)

| Concern | Rule |
|---------|------|
| IDs / time | UUIDv7 preferred; UTC in DB; user TZ at edges |
| Money | NUMERIC only for prices/money |
| Events | Outbox in same TX as state change |
| Idempotency | Keys on webhooks, notifications, jobs |
| AI safety | Untrusted docs/user text; allowlisted tools; schema validation |
| Versioning | Strategy, prompt, model, engine, dataset versions immutable once published |
| Testing | Deterministic core = unit + golden; AI = eval sets; security = RBAC/upload/exposure |
| Commits | Strategy-rule change ⇒ new strategy version + fixtures; schema ⇒ Alembic |

---

## 5. Release gates (must pass before Phase 20)

| Gate | Focus |
|------|--------|
| A Security | Auth/RBAC/secrets; private inference; restore tested |
| B Deterministic correctness | Strategy/risk fixtures; stale-data gate |
| C RAG quality | Expected sources; bounded uncertainty |
| D Vision quality | Corpus eval; no fabricated precision |
| E Backtesting | Reproducible pinned runs |
| F Paper trading | Soak without integrity defects |
| G Operations | Dashboards, DLQ, backups, kill switches, runbooks |

---

## 6. Open decisions (resolve before production alerts)

Document answers in `docs/strategy/OPEN_DECISIONS.md` as they lock:

1. Exact paper/live risk policy numbers (versioned, not hard-coded).
2. Measurable volume / retest thresholds per asset class.
3. BOS/MSB semantics (close vs wick; confirmation latency).
4. Which Wyckoff events are code vs advisory AI.
5. Forex volume-harmony proxy definition.
6. News/event blackout severities and windows.
7. Crypto weekend policy: hard rule vs configurable.
8. Futures/perp scope and leverage caps (later).
9. Target policy: structure targets vs opposite-MSB vs staged TP mix.
10. Which external research, if any, rises above Tier-5.

---

## 7. Resources still needed (track explicitly)

| Resource | Priority |
|----------|----------|
| Original screenshot ZIP | High |
| Forex-specific examples / adaptation notes | High |
| Course videos/transcripts for verbal definitions | High |
| Past trades: wins, losses, WAIT, invalid | High |
| Personal annotations (“this is / is not BOS”) | High |
| Historical crypto OHLCV (+ derivatives if licensed) | High |
| Historical Forex OHLC/spread/calendar | High |
| Economic/news feed | Medium–High |
| Instrument metadata (fees, ticks, lots, hours) | High |

---

## 8. Suggested near-term execution order (next concrete steps)

1. **Now:** Finish Phase 0 Strategy Spec v1 for crypto-only mandatory gates.
2. **In parallel:** Phase 1 repo bootstrap in this empty `agentic-trading` workspace.
3. **Then:** Phase 2 → 3 → 5 → 6 → 7 → 8 (thin vertical: one symbol, one timeframe, one strategy version).
4. **Then:** Phase 4 RAG on curated Tier-1/2 only.
5. **Then:** Phase 9 backtest that strategy version before any Telegram alerts.
6. **Defer:** Full Decision ML (10–12) until golden strategy + labels exist; start with rule-only READY_FOR_REVIEW.
7. **Defer:** Forex until Spec + provider + volume proxy decisions lock.
8. **Defer:** Mobile polish until Telegram paper loop works (mobile can scaffold earlier).

---

## 9. Definition of Done — first real release

- [ ] Private FastAPI backend with `uv` lockfile
- [ ] Postgres/pgvector, Redis, object storage, Ollama private
- [ ] Curated, tiered, citable knowledge base
- [ ] Crypto adapters → one MarketContext (Forex only if Spec-ready)
- [ ] Deterministic strategy/risk with golden tests + versioning
- [ ] Backtest without known look-ahead leakage
- [ ] Decision path issues WAIT/NO_SETUP as first-class (ML optional if Gate B met without it)
- [ ] LLM explanations use computed values + citations
- [ ] Vision verified against market data (or advisory-only if Gate D fails)
- [ ] Telegram Q&A, screenshots, alerts
- [ ] Mobile: setups, chat, journal, analytics (or explicit waiver)
- [ ] Paper soak completed
- [ ] Monitoring, backups, restore, kill switches
- [ ] No public Ollama/DB/Redis
- [ ] Live broker execution disabled

---

## 10. Final principle

Do not build “an LLM that looks at a chart and says buy or sell.”

Build a **private evidence system**:

> trusted strategy knowledge + normalized market data + deterministic features/rules + risk veto + backtesting + (optional) calibrated ML + LLM that explains and interacts

That is slower than a demo — and it is the system these specifications describe.
