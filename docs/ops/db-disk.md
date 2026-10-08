# Runbook: Database disk pressure

## Symptoms
- Postgres logs `No space left on device`; API 500s; alembic / backups fail.

## Immediate actions
1. Check volume usage for `pta_pg_data` and host disk.
2. Prefer reclaiming `data/backups` old encrypted dumps (retain policy: 14).
3. Vacuum / analyze only after confirming space headroom.
4. If critical: stop workers that write candles, keep API read-only mentally — still set `scanner_enabled=false` to halt ingest.

## Verify
- `GET /v1/ops/readiness` returns `database_ok=true`.
- Schedule encrypted backup once space recovers (`scripts/backup_postgres.sh`).
