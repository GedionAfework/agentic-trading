# Waiver log — deferred Must requirements

| Code | Requirement | Reason | Approved | Expires | Active |
|------|-------------|--------|----------|---------|--------|
| _(none yet)_ | | | | | |

Common codes:
- `gate_f_soak_incomplete` — enable live alerts before 14-day soak finishes
- `gate_f_integrity_defects` — temporary integrity exception (prefer fix instead)
- `gate_checklist_incomplete` — enable with missing gate sign-offs (discouraged)

API is source of truth: `GET /v1/release/waivers`.
