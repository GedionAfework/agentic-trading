# Source inventory

**Last updated:** 2026-10-06  
**Status:** Incomplete — design docs present; course corpus not yet in workspace

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
| STR-003 | Original screenshot ZIP (high-res charts) | **Missing** | Tier 2 / Vision dataset | Prefer over Word-embedded images |
| STR-004 | Course videos / transcripts | **Missing** | Tier 2 | Needed for verbal defs (volume, retest) |
| STR-005 | Personal annotations (“this is BOS / not BOS”) | **Missing** | Tier 3 | Highest value labels |
| STR-006 | Historical trade journal / past trades | **Missing** | Tier 3–4 | Wins, losses, WAIT, invalid |
| STR-007 | Forex-specific examples / adaptation notes | **Missing** | Tier 1–2 when approved | Explicit gap today |
| STR-008 | Risk policy notes (personal vs course) | **Missing** | Tier 1 after reconciliation | Versioned RiskPolicy |

## 3. Interim baseline (until STR-* arrive)

Until course files are attached, Strategy Spec v1 is drafted from **ENG-005** section “source baseline understood from the supplied materials” (Wyckoff + HDM + AMT). Every rule is marked `SOURCE-DERIVED (pending primary cite)` or `ENGINEERING CANDIDATE`.

**Action for owner:** copy course pack into `resources/incoming/` and reply with a short list of what you dropped (or the folder path if it lives elsewhere).

## 4. Curation checklist (per document/page)

When materials arrive, tag each page/image:

- `keep` — strategy-relevant
- `duplicate` — skip for RAG; keep pointer if needed
- `irrelevant` — exclude from production retrieval
- `quiz_only` — not strategy truth unless lesson meaning approved
- `vision_label_candidate` — good for screenshot benchmark
