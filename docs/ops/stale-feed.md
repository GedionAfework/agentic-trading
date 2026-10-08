# Runbook: Stale market feed

## Symptoms
- Scanner status shows provider `ok=false` or candles older than policy freshness window.
- Risk assessments fail closed with freshness blockers.
- Grafana / logs: rising `NO_SETUP` / skipped scans with freshness reasons.

## Immediate actions
1. Confirm kill switches — leave `scanner_enabled=true` unless feed is corrupt.
2. `GET /v1/scanner/status` and `GET /v1/markets/health` (or equivalent freshness endpoints).
3. Manually `POST /v1/markets/sync` for the affected symbol/timeframe.
4. If Binance (or upstream) is down: disable notifications (`notifications_enabled=false`) to avoid stale alerts; keep storing candidates suppressed if needed.

## Verify
- Fresh closed candle appears; scanner run succeeds without freshness blockers.
- Do **not** invent prices or widen risk to “make it trade.”

## Escalate
- Persistent multi-hour outage → document waiver; no live execution path exists to disable beyond alerts.
