# Encrypted backups and restore drill

## Targets
- **RPO ≤ 24h** — at least one successful encrypted dump per day.
- **RTO ≤ 4h** — restore drill into ephemeral DB within 14400s.

## Backup
```bash
export BACKUP_PASSPHRASE='...'   # not the JWT secret
export POSTGRES_PASSWORD='...'
./scripts/backup_postgres.sh
```
Produces `data/backups/trading-<UTC>.sql.gpg` (AES-256-CBC). Plain SQL is shredded.

## Restore drill (non-destructive)
```bash
./scripts/restore_drill.sh data/backups/trading-YYYYMMDDTHHMMSSZ.sql.gpg
```
Creates `trading_restore_drill`, loads the dump, prints `elapsed_seconds`.

## Drill log
| Date (UTC) | Operator | Elapsed (s) | Pass? | Notes |
|------------|----------|-------------|-------|-------|
| _pending first prod drill_ | | | | Run before Phase 20 |

## Notes
- Prefer logical dumps for portability; filesystem snapshots are complementary.
- Never commit passphrase or plaintext dumps.
