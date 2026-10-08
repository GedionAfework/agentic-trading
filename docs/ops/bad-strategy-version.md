# Runbook: Bad published strategy version

## Symptoms
- Spike in invalid setups, risk vetoes, or paper integrity defects tied to a new `strategy_version_no`.
- Golden fixture regressions after a publish.

## Immediate actions
1. Kill notifications: `notifications_enabled=false`.
2. Optionally pause scanner: `scanner_enabled=false`.
3. Do **not** silently edit the published version — publish a corrected new version (immutability rule).
4. Quarantine paper accepts until fixtures pass.
5. Document the bad version id in the journal / audit log.

## Verify
- Strategy golden tests green for the replacement version.
- Paper soak integrity remains ok before re-enabling alerts.
