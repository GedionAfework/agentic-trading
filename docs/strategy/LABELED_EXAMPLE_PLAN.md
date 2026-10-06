# Labeled example plan

Labels feed golden strategy tests, vision benchmarks, and (later) Decision ML. Include **losers, WAIT, and invalid** setups — not only winners.

## 1. Minimum sets for Phase 0 → Phase 7

| Set | Target count | Purpose |
|-----|--------------|---------|
| Structure/BOS | ≥ 20 charts or candle windows | STR-001/002 golden tests |
| Safer entry sequences | ≥ 10 full sequences | ENT-001 |
| Aggressive entry | ≥ 5 | ENT-002 |
| WAIT / incomplete | ≥ 15 | Prove gates block |
| Invalid / failed | ≥ 10 | Invalid negatives |
| Vision screenshot corpus | 200–500 later; **start with 30** | Symbol/TF/structure extraction |
| Outcome-labeled trades | ≥ 30 with R outcome | Journal + future ML |

## 2. Label schema (per example)

```text
example_id:
instrument:
timeframe:
decision_time_utc:
direction: LONG | SHORT | NONE
expected_action: NO_SETUP | WATCH | WAIT_FOR_CONFIRMATION | ENTER_LONG | ENTER_SHORT | ...
conditions:
  htf_aligned: true|false|unknown
  bos_confirmed: true|false|unknown
  volume_harmony: true|false|unknown
  ...
entry_zone: [low, high] | null
stop: number | null
targets: [] | null
outcome_if_known:
  first_event: TP1|TP2|TP3|SL|INVALIDATION|TIMEOUT|null
  realized_R: number | null
source_ref: course page / screenshot id / journal id
notes:
```

## 3. Process

1. Owner drops materials in `resources/incoming/`.
2. Curate pages (`keep` / `duplicate` / `irrelevant`).
3. Label in spreadsheet or YAML under `resources/labels/` (gitignored if needed).
4. Promote stable fixtures into `tests/strategy/fixtures/` once Phase 7 starts.

## 4. Immediate ask

Provide any of:

- Screenshot ZIP / chart images you already use for teaching
- 5–10 past trades with “why I took / skipped”
- Written bullets you treat as non-negotiable rules

Even a rough dump unblocks citing STRATEGY_SPEC_v1.
