from datetime import UTC, datetime

from private_trading_features.engine import compute_feature
from private_trading_features.types import CandleBar, TriState
from decimal import Decimal


def test_crypto_session_always_open() -> None:
    bar = CandleBar(
        open_time=datetime(2026, 1, 3, 12, tzinfo=UTC),  # Saturday
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
    )
    result = compute_feature("crypto_session_open", [bar], 0)
    assert result.status == TriState.TRUE
    assert result.value is True
