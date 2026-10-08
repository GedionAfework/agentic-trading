# Runbook: Credential / secret leak

## Symptoms
- Secret scan CI fails; token observed in chat/logs; unexpected auth from unknown device.

## Immediate actions
1. Rotate immediately: `JWT_SECRET`, DB password, object storage keys, Telegram bot token + webhook secret, metrics bearer token.
2. Revoke all sessions (`/v1/auth/sessions` revoke loops) for owner/admin.
3. Set `notifications_enabled=false` and `scanner_enabled=false` until blast radius known.
4. Invalidate Telegram link challenges; re-link accounts after bot token rotate.
5. Audit `audit_events` for suspicious actions around the leak window.

## Verify
- `uv run python scripts/secret_scan.py` clean.
- Production settings guard passes (`production_settings_errors` empty).
- Re-enable kill switches only after rotation confirmed.
