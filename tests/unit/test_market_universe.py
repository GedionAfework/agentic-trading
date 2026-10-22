from private_trading_market_data.universe import (
    CORE_CRYPTO_SYMBOLS,
    CORE_FOREX_SYMBOLS,
    CORE_MARKET_SYMBOLS,
    OWNER_CRYPTO_SYMBOLS,
    asset_class_for_symbol,
)


def test_core_market_universe_is_unique_and_asset_aware() -> None:
    assert CORE_CRYPTO_SYMBOLS == ("BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT")
    assert OWNER_CRYPTO_SYMBOLS == CORE_CRYPTO_SYMBOLS
    assert len(CORE_FOREX_SYMBOLS) == 8
    assert len(CORE_MARKET_SYMBOLS) == 12
    assert len(set(CORE_MARKET_SYMBOLS)) == 12
    assert asset_class_for_symbol("BTC/USDT") == "crypto"
    assert asset_class_for_symbol("DOGE/USDT") == "crypto"
    assert asset_class_for_symbol("EUR/USD") == "forex"
    assert asset_class_for_symbol("BNB/USDT") is None
