# STRIDE controls (Architecture Appendix D mapping)

Verified for Phase 19 baseline. “Verified” means control exists in code/infra/docs — not a third-party pentest.

| Threat | Control | Evidence |
|--------|---------|----------|
| **S**poofing | JWT sessions + refresh rotation; Telegram webhook secret; MFA hooks in identity model | `/v1/auth/*`, telegram webhook validation |
| **T**ampering | Immutable published strategy/risk versions; audit log; alembic migrations | strategy publish flow, `audit_events` |
| **R**epudiation | Append-only audit + paper trade events | `record_audit`, `paper_trade_events` |
| **I**nformation disclosure | Private binds; nginx TLS; metrics optional bearer; no secrets in mobile | `docker-compose.prod.yml`, SecureStore |
| **D**enial of service | Nginx `limit_req` + API sliding-window limits; upload size cap 8MB | `infra/nginx`, `rate_limit.py`, vision validate |
| **E**levation of privilege | RBAC owner/admin/viewer; kill switches owner/admin only | `CurrentUser.require_roles` |

## Explicit non-goals (still safe)
- No live broker credentials in baseline.
- LLM/VLM cannot override strategy/risk gates.
- Analytics cohorts never silently merge.
