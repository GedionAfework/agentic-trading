# Source inventory

**Last updated:** 2026-10-08  
**Status:** Partial — screenshot ZIP ingested; PDFs/playbook still missing

## 1. Engineering / product specs (available)

| ID | File | Location | Role | Authority |
|----|------|----------|------|-----------|
| ENG-001 | Private Trading AI SRS Detailed | Downloads / extracted `tmp/pdfs/` | Product requirements | Tier Ops (not strategy truth) |
| ENG-002 | Private Trading AI SDS Detailed | Downloads / extracted `tmp/pdfs/` | Software design | Tier Ops |
| ENG-003 | Architecture Design Detailed | Downloads / extracted `tmp/pdfs/` | System architecture | Tier Ops |
| ENG-004 | Database Design Detailed | Downloads / extracted `tmp/pdfs/` | Schema | Tier Ops |
| ENG-005 | Complete Implementation Roadmap | Downloads / extracted `tmp/pdfs/` | Build plan + strategy summary | Tier Ops; strategy summary is **secondary** until primary course files are attached |

## 2. Strategy / course materials (needed)

Drop into `resources/incoming/` and fill this table.

| ID | Expected material | Status | Suggested authority | Notes |
|----|-------------------|--------|---------------------|-------|
| STR-001 | Approved written strategy rules / playbook | **Missing** | Tier 1 | Becomes primary rule source |
| STR-002 | Original course modules (PDF/DOCX) | **Missing** | Tier 2 | Curate before RAG |
| STR-003 | Original screenshot ZIP (high-res charts) | **In workspace** | Tier 2 / Vision dataset | 480 PNGs at `resources/incoming/telegram_screenshots_2025-2026/` (~15–25% live charts, rest course slides). Review: `CORPUS_REVIEW.md` |
| STR-004 | Course videos / transcripts | **Missing** (stills only) | Tier 2 | Lesson-frame stills (Wyckoff glossary, VPA, AMT); full video/transcript still needed |
| STR-005 | Personal annotations (“this is BOS / not BOS”) | **Partial** | Tier 3 | Best labeled: `2025-12-15 145256` BTCUSDT.P 15m BOS short (retest vs confirm). MSB close-based teaching `2025-11-24 022309`. May BNB 1h demand-zone longs with RR boxes |
| STR-006 | Historical trade journal / past trades | **Partial** | Tier 3–4 | May BNB long series includes in-profit (`2026-05-27 035340`) and failed (`2026-05-28 035726`) frames — not a full journal |
| STR-007 | Forex-specific examples / adaptation notes | **Missing** | Tier 1–2 when approved | Sampled charts are crypto (BTC/BNB); no FX in 61-image sample |
| STR-008 | Risk policy notes (personal vs course) | **Partial (slides)** | Tier 1 after reconciliation | Psych/expectancy slides (≤50% WR OK); no personal numeric risk policy |

## 3. Interim baseline (until STR-* arrive)

Strategy Spec v1 remains crypto-first (Wyckoff + HDM + AMT). Screenshot ZIP now supplies **primary-cite candidates** for:

- Close-based **MSB/BOS** (feeds D-03) plus a 15m BOS short playbook (perp — D-08 still spot-first)
- **VPA** harmony/divergence and volume-at-trend-end
- Wyckoff lexicon + AMT value-area reclaim (VAL→VAH, no retest required)
- Live habit: EMA 12/21/50, demand boxes, Long Position RR (May BNBUSDT 1h)

Rules still need promotion into measurable defs before they authorize ENTER. Deduplicate Dec `* - Copy.png` and near-identical May BNB frames before labeling.

**Action for owner:** still useful — course PDFs/DOCX, forex chart examples, and a full outcome journal. Screenshot ZIP is already under `resources/incoming/` (gitignored). Rotate any password shown in early Oct/Nov onboarding shots.

## 4. Curation checklist (per document/page)

When materials arrive, tag each page/image:

- `keep` — strategy-relevant
- `duplicate` — skip for RAG; keep pointer if needed
- `irrelevant` — exclude from production retrieval
- `quiz_only` — not strategy truth unless lesson meaning approved
- `vision_label_candidate` — good for screenshot benchmark
