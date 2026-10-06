from datetime import UTC, datetime

from private_trading_market_data.sessions import active_forex_sessions, is_market_open


def test_crypto_always_open() -> None:
    assert is_market_open("crypto") is True


def test_fx_weekend_closed() -> None:
    saturday = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)  # Saturday
    assert is_market_open("fx", saturday) is False


def test_fx_london_session() -> None:
    wednesday = datetime(2026, 1, 7, 10, 0, tzinfo=UTC)
    assert is_market_open("fx", wednesday) is True
    assert "london" in active_forex_sessions(wednesday)
