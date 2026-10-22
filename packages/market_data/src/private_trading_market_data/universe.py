"""Versioned market universes used by research, routing, and paper trading."""

from __future__ import annotations

# Owner publish set (2026-10-13): BTC, ETH, SOL, DOGE.
CORE_CRYPTO_SYMBOLS: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "DOGE/USDT",
)

# Alias for agent/scanner scope docs and routing helpers.
OWNER_CRYPTO_SYMBOLS: tuple[str, ...] = CORE_CRYPTO_SYMBOLS

CORE_FOREX_SYMBOLS: tuple[str, ...] = (
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "EUR/GBP",
)

CORE_MARKET_SYMBOLS: tuple[str, ...] = CORE_CRYPTO_SYMBOLS + CORE_FOREX_SYMBOLS


def asset_class_for_symbol(symbol: str) -> str | None:
    if symbol in CORE_CRYPTO_SYMBOLS:
        return "crypto"
    if symbol in CORE_FOREX_SYMBOLS:
        return "forex"
    return None
