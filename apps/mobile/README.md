# Private Trading — Mobile (Expo)

Phase 17 rich client. Talks **only** to the private FastAPI API. No Telegram/Ollama/DB secrets in the app.

## Screens (SRS Appendix A)

| Screen | Route | Notes |
|--------|-------|-------|
| Login | `/login` | SecureStore tokens; refresh on 401 |
| Dashboard | `/(app)` | Scanner + paper soak summary |
| Setups list/detail | `/(app)/setups` | Accept ENTER → PAPER trade |
| Ask AI | `/(app)/ask` | Knowledge citations |
| Screenshot | `/(app)/vision` | Upload; vision never authorizes trade |
| Knowledge | `/(app)/knowledge` | Document list |
| Strategies | `/(app)/strategies` | Read-only |
| Backtests | `/(app)/backtests` | Job list |
| Paper portfolio | `/(app)/paper` | PAPER-labeled equity/trades |
| Journal | `/(app)/journal` | paper cohort only |
| Analytics | `/(app)/analytics` | Placeholder until Phase 18 |
| Notifications | `/(app)/notifications` | Telegram status |
| Sessions | `/(app)/sessions` | Revoke |
| System health | `/(app)/health` | API + scanner |

Deep link scheme: `privatetrading://` (e.g. `privatetrading://setups/<id>`).

## Run

```bash
# API must be up (host machine)
uv run uvicorn private_trading_api.main:app --app-dir apps/api/src --host 0.0.0.0 --port 8000

cd apps/mobile
cp .env.example .env   # set EXPO_PUBLIC_API_BASE_URL for your device
npm start
```

API base URL hints:

- iOS simulator: `http://127.0.0.1:8000/v1`
- Android emulator: `http://10.0.2.2:8000/v1`
- Physical device: `http://<lan-ip>:8000/v1` (API bound to `0.0.0.0`)

```bash
npm run typecheck
```

## Safety

- Tokens in SecureStore (native) / localStorage (web only for smoke)
- HTTPS required for production builds
- PAPER trades are always labeled
- Push notifications / EAS device builds are operational follow-ups (credentials not in repo)
