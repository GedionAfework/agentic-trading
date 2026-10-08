# Operations runbooks (Gate G)

These runbooks support Phase 19 production hardening. Prefer measured SQL / metrics over guesses.

| Runbook | Trigger |
|---------|---------|
| [stale-feed.md](./stale-feed.md) | Market freshness / scanner skip |
| [gpu-down.md](./gpu-down.md) | Ollama / VLM unavailable |
| [telegram-429.md](./telegram-429.md) | Telegram rate limits |
| [db-disk.md](./db-disk.md) | Postgres disk pressure |
| [credential-leak.md](./credential-leak.md) | Suspected secret exposure |
| [bad-strategy-version.md](./bad-strategy-version.md) | Bad published strategy |
| [BACKUP_RESTORE.md](./BACKUP_RESTORE.md) | Encrypted backup + restore drill |
| [FIREWALL.md](./FIREWALL.md) | Host firewall / private binds |
| [STRIDE_CONTROLS.md](./STRIDE_CONTROLS.md) | Architecture Appendix D mapping |
| [PRODUCTION_READINESS.md](./PRODUCTION_READINESS.md) | Gates A + G sign-off |
| [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) | Phase 20 live alerts (no broker execution) |
| [WAIVERS.md](./WAIVERS.md) | Deferred Must log |

Kill switches: `PUT /v1/scanner/switches` (`scanner_enabled`, `notifications_enabled`) — owner/admin only.
Live alerts: `POST /v1/release/live-alerts` after Gates A–G + soak (or waivers).
