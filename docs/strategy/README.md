# Phase 0 — Strategy specification workspace

**Status:** In progress (draft from design docs; pending owner course materials)  
**Gate:** No coding of trade decisions until every mandatory entry/exit term has a deterministic definition or explicit `AI-only/advisory` status.

## Documents in this folder

| File | Purpose |
|------|---------|
| [SOURCE_INVENTORY.md](./SOURCE_INVENTORY.md) | What source files we have / still need |
| [AUTHORITY_TIERS.md](./AUTHORITY_TIERS.md) | Which sources can override which |
| [GLOSSARY.md](./GLOSSARY.md) | Strategy concept definitions |
| [CONFLICTS_AND_GAPS.md](./CONFLICTS_AND_GAPS.md) | Risk conflicts + Forex gaps |
| [MEASURABLE_DEFINITION_BACKLOG.md](./MEASURABLE_DEFINITION_BACKLOG.md) | English terms → measurable rules |
| [STRATEGY_SPEC_v1.md](./STRATEGY_SPEC_v1.md) | Executable strategy specification (crypto-first) |
| [OPEN_DECISIONS.md](./OPEN_DECISIONS.md) | Decisions that must lock before production alerts |
| [LABELED_EXAMPLE_PLAN.md](./LABELED_EXAMPLE_PLAN.md) | Plan for golden fixtures / vision / ML labels |

## How to complete Phase 0

1. Drop course PDFs/DOCX/screenshot ZIPs/transcripts into `resources/incoming/`.
2. Update `SOURCE_INVENTORY.md` with real filenames and authority tiers.
3. Walk each rule in `STRATEGY_SPEC_v1.md` and attach source refs (doc/page).
4. Resolve or defer each row in `OPEN_DECISIONS.md` and `MEASURABLE_DEFINITION_BACKLOG.md`.
5. Owner sign-off on Strategy Spec v1 → Phase 1 (repo bootstrap) can proceed in parallel even before full sign-off, but **no strategy engine coding** until the gate passes.

## Legend used in specs

- **SOURCE-DERIVED** — from your course/framework materials (via Implementation Roadmap baseline until files are attached).
- **ENGINEERING CANDIDATE** — proposed measurable definition; must be validated against examples before lock.
- **OWNER DECISION** — needs your explicit choice.
- **GAP** — not specified by current sources; must not be silently invented.
