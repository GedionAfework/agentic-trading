# Phase 20 — Live recommendation release checklist

Alerts only. Automated broker execution remains **disabled** (FR-SIG-008, BR-005).

## Preconditions
1. Gates A–G signed via `POST /v1/release/signoffs` (`gate`: A…G).
2. Paper soak complete (`GET /v1/paper/account` → `soak.complete=true`) **or** active waiver `gate_f_soak_incomplete`.
3. Paper integrity ok **or** waiver `gate_f_integrity_defects`.
4. `GET /v1/ops/readiness` → `broker_execution.ok=true`.
5. Narrow policy: approved symbols/TFs, quiet hours, Telegram channel only.

## Enable
```bash
# Review status
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/release/status

# Sign each gate A–G (owner/admin)
curl -X POST .../v1/release/signoffs -d '{"gate":"A","notes":"..."}'

# Enable production alert mode
curl -X POST .../v1/release/live-alerts -d '{"enabled":true}'
```

Lab/dev alerts continue when `live_alerts_enabled=false` (kill switch still applies).

## Scope defaults
| Knob | Default |
|------|---------|
| Symbols | BTC/USDT, ETH/USDT |
| Timeframes | 15m, 1h |
| Actions | ENTER only (+ risk approved, confidence ≥ medium) |
| Quiet hours UTC | 22:00–06:00 |
| Channels | telegram |

## Waivers
Deferred Musts go in `POST /v1/release/waivers` and `docs/ops/WAIVERS.md` — never silent.
