from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from private_trading_market_data.contracts import (
    InstrumentInfo,
    NormalizedCandle,
    ProviderHealth,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider adapters return normalized contracts only — never raw exchange JSON."""

    code: str

    async def health(self) -> ProviderHealth: ...

    async def list_instruments(self) -> list[InstrumentInfo]: ...

    async def fetch_candles(
        self,
        *,
        provider_symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedCandle]: ...

    async def aclose(self) -> None: ...
