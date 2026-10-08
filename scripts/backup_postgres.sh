#!/usr/bin/env bash
# Encrypted Postgres logical backup (Gate G / Gate A restore prerequisite).
# Requires: docker, openssl, POSTGRES_PASSWORD (prod), BACKUP_PASSPHRASE
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${BACKUP_DIR:-$ROOT/data/backups}"
mkdir -p "$OUT_DIR"
RAW="$OUT_DIR/trading-${STAMP}.sql"
ENC="$RAW.gpg"

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE for encryption}"

echo "dumping trading database…"
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-trading}" pta-postgres \
  pg_dump -U trading -d trading --no-owner --format=plain > "$RAW"

echo "encrypting with AES-256…"
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in "$RAW" -out "$ENC" -pass pass:"$BACKUP_PASSPHRASE"
shred -u "$RAW" 2>/dev/null || rm -f "$RAW"

# Keep last 14 encrypted dumps by default
ls -1t "$OUT_DIR"/trading-*.sql.gpg 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "wrote $ENC"
echo "RPO target: <=24h (schedule this via cron/systemd timer)"
