# Runbook: Telegram HTTP 429

## Symptoms
- Notification deliveries stuck with retry / backoff.
- Bot replies delayed; delivery logs show `TelegramTransientError` or 429.

## Immediate actions
1. Do **not** disable the bot token and recreate casually (link challenges break).
2. Confirm delivery worker respects backoff (`packages/notifications` delivery module).
3. Temporarily set `notifications_enabled=false` if the queue is meltdown-level; candidates still store.
4. Reduce alert fan-out (quiet hours / narrower symbols) before Phase 20 go-live.

## Verify
- Backlog drains without duplicate alert spam (idempotency keys).
- After recovery, re-enable notifications and spot-check one alert.
