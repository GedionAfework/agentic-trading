"""Market data providers and normalization."""

from private_trading_market_data.contracts import (
    MarketSnapshot,
    NormalizedCandle,
    ProviderHealth,
)
from private_trading_market_data.providers import BinanceSpotProvider
from private_trading_market_data.universe import (
    CORE_CRYPTO_SYMBOLS,
    CORE_FOREX_SYMBOLS,
    CORE_MARKET_SYMBOLS,
    OWNER_CRYPTO_SYMBOLS,
    asset_class_for_symbol,
)

__all__ = [
    "BinanceSpotProvider",
    "CORE_CRYPTO_SYMBOLS",
    "CORE_FOREX_SYMBOLS",
    "CORE_MARKET_SYMBOLS",
    "OWNER_CRYPTO_SYMBOLS",
    "MarketSnapshot",
    "NormalizedCandle",
    "ProviderHealth",
    "asset_class_for_symbol",
]
__version__ = "0.1.0"
