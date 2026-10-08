from __future__ import annotations

import asyncio
from typing import Any

from private_trading_core.config import get_settings
from private_trading_core.logging import configure_logging, get_logger
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_notifications.delivery import dispatch
from private_trading_notifications.repository import process_update
from private_trading_notifications.telegram_client import (
    TelegramTransientError,
    build_client,
)

logger = get_logger(__name__)


def _timeframes() -> tuple[str, ...]:
    settings = get_settings()
    parsed = tuple(
        tf.strip() for tf in settings.market_default_timeframes.split(",") if tf.strip()
    )
    return parsed or ("15m", "1h")


async def poll_forever(*, long_poll_seconds: int = 25, dispatch_every: int = 2) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set; nothing to poll.")
    client = build_client(
        token=settings.telegram_bot_token, base_url=settings.telegram_api_base_url
    )
    factory = get_session_factory()
    offset: int | None = None
    loops = 0
    try:
        while True:
            loops += 1
            try:
                updates: list[dict[str, Any]] = await client.get_updates(
                    offset=offset, timeout=long_poll_seconds
                )
            except TelegramTransientError as exc:
                logger.warning("telegram_poll_transient error=%s", exc.message)
                await asyncio.sleep(5)
                continue
            for update in updates:
                offset = max(offset or 0, int(update.get("update_id", 0)) + 1)
                async with factory() as session:
                    result = await process_update(
                        session,
                        update,
                        settings=settings,
                        client=client,
                        timeframes=_timeframes(),
                    )
                logger.info("telegram_update handled=%s", result.get("handled"))
            if loops % dispatch_every == 0:
                async with factory() as session:
                    summary = await dispatch(session, client=client)
                logger.info("telegram_dispatch %s", summary)
    finally:
        await client.aclose()
        await dispose_engine()


def main() -> None:
    configure_logging()
    asyncio.run(poll_forever())
