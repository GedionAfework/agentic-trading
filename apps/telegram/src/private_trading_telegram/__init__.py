"""Telegram bot entrypoint.

Production path: Telegram → `POST /v1/telegram/webhook` (API) with the shared secret header.
Fallback for hosts without a public URL: `uv run python -m private_trading_telegram`
long-polls getUpdates and runs the same `process_update` handler plus the alert dispatcher.
"""

__version__ = "0.1.0"
