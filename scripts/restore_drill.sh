#!/usr/bin/env bash
# Restore drill into an ephemeral database (does not clobber production).
# Measures wall time toward RTO <= 4h baseline.
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE}"
: "${1:?Usage: restore_drill.sh path/to/trading-UTC.sql.gpg}"

ENC="$1"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
START="$(date +%s)"

openssl enc -d -aes-256-cbc -pbkdf2 -in "$ENC" -out "$TMP/restore.sql" \
  -pass pass:"$BACKUP_PASSPHRASE"

DRILL_DB="trading_restore_drill"
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-trading}" pta-postgres \
  psql -U trading -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${DRILL_DB};" \
  -c "CREATE DATABASE ${DRILL_DB};"

docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-trading}" pta-postgres \
  psql -U trading -d "$DRILL_DB" < "$TMP/restore.sql"

END="$(date +%s)"
ELAPSED=$((END - START))
echo "restore_drill_ok database=${DRILL_DB} elapsed_seconds=${ELAPSED}"
echo "RTO budget: 14400 seconds (4h). Record this run in docs/ops/BACKUP_RESTORE.md"
