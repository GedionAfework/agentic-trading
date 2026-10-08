#!/usr/bin/env bash
# Local external-exposure smoke: data plane must not listen on 0.0.0.0.
set -euo pipefail

fail=0
check_port() {
  local port="$1"
  local name="$2"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn | awk '{print $4}' | grep -E "0\.0\.0\.0:${port}$|\[::\]:${port}$" >/dev/null; then
      echo "FAIL $name publicly bound on :$port"
      fail=1
    else
      echo "OK   $name not publicly bound on :$port"
    fi
  else
    echo "SKIP ss not available; verify $name:$port manually"
  fi
}

check_port 5432 postgres
check_port 5433 postgres_mapped
check_port 6379 redis
check_port 6380 redis_mapped
check_port 11434 ollama
check_port 9000 object_storage

if [[ "$fail" -ne 0 ]]; then
  echo "exposure_scan FAILED — bind data plane to 127.0.0.1 (docker-compose.prod.yml)"
  exit 1
fi
echo "exposure_scan OK"
