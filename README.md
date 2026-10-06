# Private Self-Hosted AI Trading Copilot

Decision-support trading platform: private RAG, deterministic strategy/risk engines, self-hosted LLM/VLM, Telegram + mobile. **No live broker execution in baseline.**

See [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) and [`docs/strategy/`](docs/strategy/).

## Prerequisites

- Python 3.12 (via [uv](https://github.com/astral-sh/uv))
- Docker Desktop (Postgres/pgvector, Redis, MinIO)
- Optional later: Ollama with a local GPU

## Quick start

```bash
# 1. Install deps
uv sync --group dev

# 2. Environment
cp .env.example .env

# 3. Infrastructure (start Docker Desktop first on Windows)
# Postgres host port 5433, Redis 6380, S3 mock 9000
# (avoids clashes with other local stacks; MinIO Hub pulls are often denied)
docker compose -f infra/docker/docker-compose.yml up -d

# 4. API
uv run uvicorn private_trading_api.main:app --reload --app-dir apps/api/src

# 5. Health
curl http://127.0.0.1:8000/health

# 6. Tests
uv run pytest
uv run ruff check .
```

## Repository layout

```
apps/           # api, worker, telegram entrypoints
packages/       # domain libraries (core, db, market_data, strategies, ...)
infra/docker/   # Compose stack
docs/           # roadmap + Phase 0 strategy specs
migrations/     # Alembic (Phase 2)
tests/          # unit / integration / ...
resources/      # local course dumps (gitignored under incoming/)
```

## Current phase

**Phase 1 — Repository & developer tooling** (in progress / landing).
