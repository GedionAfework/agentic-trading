"""Celery application — market, ai, notifications, backtests queues."""

from __future__ import annotations

import asyncio
from typing import Any

from private_trading_core.config import get_settings

try:
    from celery import Celery
    from celery.schedules import schedule
    from kombu import Queue
except ImportError:  # pragma: no cover
    Celery = None  # type: ignore[misc, assignment]
    Queue = None  # type: ignore[misc, assignment]
    schedule = None  # type: ignore[misc, assignment]

QUEUE_NAMES = ("market", "ai", "notifications", "backtests")
SCAN_INTERVAL_SECONDS = 60


def _timeframes() -> tuple[str, ...]:
    settings = get_settings()
    parsed = tuple(
        tf.strip() for tf in settings.market_default_timeframes.split(",") if tf.strip()
    )
    return parsed or ("15m", "1h")


def _run(coro_factory):
    return asyncio.run(coro_factory())


async def _scan_all_async(symbols: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    from private_trading_agents.scanner_service import scan_all
    from private_trading_db.session import dispose_engine, get_session_factory

    from private_trading_worker.locks import scan_lock

    settings = get_settings()
    async with scan_lock(settings.redis_url, "scanner:scan_all", ttl_seconds=55) as acquired:
        if not acquired:
            return [{"status": "skipped_locked"}]
        factory = get_session_factory()
        try:
            async with factory() as session:
                return await scan_all(session, timeframes=_timeframes(), symbols=symbols)
        finally:
            await dispose_engine()


async def _sync_all_async() -> list[dict[str, Any]]:
    from private_trading_db.session import dispose_engine, get_session_factory
    from private_trading_market_data.catalog import ensure_binance_catalog, list_enabled_instruments
    from private_trading_market_data.ingest import sync_instrument_candles
    from private_trading_market_data.providers import BinanceSpotProvider

    settings = get_settings()
    provider = BinanceSpotProvider(
        base_url=settings.binance_base_url, timeout_seconds=settings.market_http_timeout_seconds
    )
    results: list[dict[str, Any]] = []
    factory = get_session_factory()
    try:
        async with factory() as session:
            await ensure_binance_catalog(session)
            await session.commit()
            for instrument in await list_enabled_instruments(session):
                for timeframe in _timeframes():
                    try:
                        out = await sync_instrument_candles(
                            session,
                            provider,
                            canonical_symbol=instrument.canonical_symbol,
                            timeframe=timeframe,
                            limit=200,
                        )
                        results.append(
                            {
                                "symbol": out.instrument_symbol,
                                "timeframe": out.timeframe,
                                "upserted": out.upserted,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 — provider failures are status
                        await session.rollback()
                        results.append(
                            {
                                "symbol": instrument.canonical_symbol,
                                "timeframe": timeframe,
                                "error": f"{type(exc).__name__}: {exc}"[:300],
                            }
                        )
    finally:
        await provider.aclose()
        await dispose_engine()
    return results


def create_celery_app():
    if Celery is None:
        raise RuntimeError("celery is not installed; run `uv sync`")
    settings = get_settings()
    app = Celery("private_trading", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.update(
        task_default_queue="market",
        task_queues=tuple(Queue(name) for name in QUEUE_NAMES),
        task_routes={
            "scanner.sync_all": {"queue": "market"},
            "scanner.scan_all": {"queue": "market"},
            "scanner.scan_symbols": {"queue": "market"},
        },
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_time_limit=240,
        timezone="UTC",
        beat_schedule={
            "sync-candles": {
                "task": "scanner.sync_all",
                "schedule": schedule(run_every=SCAN_INTERVAL_SECONDS),
            },
            "scan-closed-candles": {
                "task": "scanner.scan_all",
                "schedule": schedule(run_every=SCAN_INTERVAL_SECONDS),
            },
        },
    )

    @app.task(name="scanner.sync_all", bind=True, max_retries=2, default_retry_delay=15)
    def sync_all_task(self):  # type: ignore[no-untyped-def]
        return _run(_sync_all_async)

    @app.task(name="scanner.scan_all", bind=True, max_retries=0)
    def scan_all_task(self):  # type: ignore[no-untyped-def]
        return _run(_scan_all_async)

    @app.task(name="scanner.scan_symbols", bind=True, max_retries=0)
    def scan_symbols_task(self, symbols: list[str]):  # type: ignore[no-untyped-def]
        return _run(lambda: _scan_all_async(tuple(symbols)))

    return app


try:
    celery_app = create_celery_app()
except RuntimeError:  # pragma: no cover
    celery_app = None


def run_scanner_loop(interval_seconds: int = SCAN_INTERVAL_SECONDS) -> None:
    """Fallback loop when Celery/Redis are unavailable. Same code path, no broker."""
    import time

    while True:
        _run(_sync_all_async)
        _run(_scan_all_async)
        time.sleep(interval_seconds)
