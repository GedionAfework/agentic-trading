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

## Auth bootstrap (Phase 2)

```bash
uv run alembic upgrade head
uv run pta-seed-owner --email owner@example.com --password changeme-owner
# Login
curl -X POST http://127.0.0.1:8000/v1/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"owner@example.com\",\"password\":\"changeme-owner\"}"
```

## Private AI gateway (Phase 3)

Ollama must stay on the private host network (default `127.0.0.1:11434`). The API is the only caller.

```powershell
# Start Ollama (Windows app or):
ollama serve

# Pull baseline models (adjust size to your GPU/RAM)
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# Authenticated smoke (owner/admin token required)
# GET  /v1/ai/health
# POST /v1/ai/smoke/generate
# POST /v1/ai/smoke/embed
```

## Knowledge / RAG (Phase 4)

```powershell
# Upload (multipart) -> status draft after embed
# POST /v1/knowledge/documents
# Approve before retrieval
# POST /v1/knowledge/documents/{id}/approve
# Ask with citations (approved corpus only)
# POST /v1/knowledge/ask
```

Objects are stored under `data/objects/` locally (gitignored). Only **approved** docs are retrieved.

## Current phase

**Phase 4 — Knowledge/RAG** (landing). Next: Phase 5 Market data core.
