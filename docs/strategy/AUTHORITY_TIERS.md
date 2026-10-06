# Authority tiers for knowledge and rules

Retrieval and strategy encoding must prefer higher tiers. A lower-tier public article must never silently override an approved Tier-1 rule.

| Tier | Name | Examples | Can define hard trade gates? |
|------|------|----------|------------------------------|
| **1** | Approved strategy rules | Owner-approved playbook, published `strategy_versions` | **Yes** |
| **2** | Original course material | Paid course modules, approved transcripts | Only after promotion into Tier 1 |
| **3** | User annotations & labeled examples | “This is BOS”, marked charts | Labels for tests/ML; not silent rule overrides |
| **4** | Historical trades & generated evaluations | Journal, backtest artifacts | Outcomes / analytics; not new rules |
| **5** | Supplementary public research | Books, free articles, web notes | Never overrides Tier 1; RAG advisory only |

## Promotion rule

```
Tier 2/3 insight → owner review → written into STRATEGY_SPEC / strategy_version → Tier 1
```

## Conflicts

If two Tier-2 passages conflict, Knowledge Agent must return `conflicts[]` + `sufficient_evidence: false` rather than inventing a resolution. Owner resolves into Tier 1.
