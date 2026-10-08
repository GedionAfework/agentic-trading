"""Telegram, push, in-app notifications.

Telegram bot logic lives here (not in apps/telegram) so the API webhook, the Celery
dispatcher and the long-polling fallback all share one implementation.
"""

from private_trading_notifications.bot import BotReply, HandledUpdate, handle_update
from private_trading_notifications.delivery import (
    MAX_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    apply_send_result,
)
from private_trading_notifications.link import (
    challenge_is_valid,
    generate_link_code,
    hash_link_code,
)
from private_trading_notifications.telegram_client import (
    DryRunTelegramClient,
    TelegramClient,
    TelegramPermanentError,
    TelegramRateLimited,
    TelegramTransientError,
    webhook_authorized,
)

__version__ = "0.1.0"

__all__ = [
    "BotReply",
    "HandledUpdate",
    "handle_update",
    "MAX_ATTEMPTS",
    "RETRY_BACKOFF_SECONDS",
    "apply_send_result",
    "challenge_is_valid",
    "generate_link_code",
    "hash_link_code",
    "DryRunTelegramClient",
    "TelegramClient",
    "TelegramPermanentError",
    "TelegramRateLimited",
    "TelegramTransientError",
    "webhook_authorized",
]
