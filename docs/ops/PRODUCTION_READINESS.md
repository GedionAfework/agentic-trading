# Production readiness report — Gates A + G

**Date:** October 2026  
**Scope:** Phase 19 hardening for private self-hosted copilot (alerts later in Phase 20; no broker execution).

## Gate A — Security

| Check | Status | Notes |
|-------|--------|-------|
| Auth / RBAC | Pass | JWT + roles; session revoke |
| Secrets hygiene | Pass (dev defaults blocked in prod) | `production_settings_errors`; CI `secret_scan` |
| Private inference / data plane | Pass (config) | loopback binds in `docker-compose.prod.yml` |
| TLS termination | Pass (config) | `infra/nginx` TLS 1.2/1.3 + HSTS |
| Upload abuse | Pass | 8MB + content sniff; 413 on Content-Length |
| Rate limits | Pass | API middleware + nginx zones |
| Restore tested | Pending ops drill | Scripts ready; log first drill in BACKUP_RESTORE.md |
| External exposure scan | Pass (script) | `scripts/exposure_scan.sh` |

## Gate G — Operations

| Check | Status | Notes |
|-------|--------|-------|
| Dashboards | Pass (scaffold) | Prometheus scrape `/metrics`; Grafana overview |
| DLQ | Pass (prior) | Scanner dead letters in status |
| Backups | Pass (script) | Encrypted `backup_postgres.sh` |
| Kill switches | Pass | `/v1/scanner/switches` + readiness surface |
| Runbooks | Pass | `docs/ops/*` |

## Residual risks / waivers
1. First encrypted restore drill must be logged before Phase 20 alert enablement.
2. Multi-worker API rate limits need nginx (in-process limiter is per worker).
3. GPU / redis / postgres exporters are optional — business metrics start with API counters.

## Sign-off
| Role | Name | Date | Gate |
|------|------|------|------|
| Owner | _pending_ | | A |
| Owner | _pending_ | | G |

Broker execution remains **disabled** / undeployed.
