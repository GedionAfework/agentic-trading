from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


@asynccontextmanager
async def scan_lock(redis_url: str, key: str, *, ttl_seconds: int = 55) -> AsyncIterator[bool]:
    """Redis SET NX lock. If Redis is unreachable, proceed — DB unique scan_runs still dedupe."""
    try:
        import redis.asyncio as aioredis
    except ImportError:  # pragma: no cover
        yield True
        return
    client = aioredis.from_url(redis_url, socket_connect_timeout=1.5, socket_timeout=1.5)
    acquired = True
    held = False
    try:
        try:
            held = bool(await client.set(key, "1", nx=True, ex=ttl_seconds))
            acquired = held
        except Exception:  # noqa: BLE001 — broker down: fall back to DB idempotency
            acquired = True
        yield acquired
    finally:
        if held:
            with contextlib.suppress(Exception):
                await client.delete(key)
        await client.aclose()
