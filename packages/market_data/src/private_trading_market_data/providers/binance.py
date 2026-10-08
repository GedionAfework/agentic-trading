from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from private_trading_core.errors import AppError

from private_trading_market_data.contracts import (
    InstrumentInfo,
    NormalizedCandle,
    ProviderHealth,
    SUPPORTED_TIMEFRAMES,
)

DEFAULT_SYMBOLS: tuple[InstrumentInfo, ...] = (
    InstrumentInfo("BTC/USDT", "crypto", "BTC", "USDT", "BTCUSDT"),
    InstrumentInfo("ETH/USDT", "crypto", "ETH", "USDT", "ETHUSDT"),
    InstrumentInfo("BNB/USDT", "crypto", "BNB", "USDT", "BNBUSDT"),
    InstrumentInfo("SOL/USDT", "crypto", "SOL", "USDT", "SOLUSDT"),
    InstrumentInfo("XRP/USDT", "crypto", "XRP", "USDT", "XRPUSDT"),
    InstrumentInfo("ADA/USDT", "crypto", "ADA", "USDT", "ADAUSDT"),
    InstrumentInfo("DOGE/USDT", "crypto", "DOGE", "USDT", "DOGEUSDT"),
    InstrumentInfo("LTC/USDT", "crypto", "LTC", "USDT", "LTCUSDT"),
    InstrumentInfo("LINK/USDT", "crypto", "LINK", "USDT", "LINKUSDT"),
    InstrumentInfo("AVAX/USDT", "crypto", "AVAX", "USDT", "AVAXUSDT"),
    InstrumentInfo("DOT/USDT", "crypto", "DOT", "USDT", "DOTUSDT"),
    InstrumentInfo("ATOM/USDT", "crypto", "ATOM", "USDT", "ATOMUSDT"),
    InstrumentInfo("NEAR/USDT", "crypto", "NEAR", "USDT", "NEARUSDT"),
    InstrumentInfo("UNI/USDT", "crypto", "UNI", "USDT", "UNIUSDT"),
    InstrumentInfo("TRX/USDT", "crypto", "TRX", "USDT", "TRXUSDT"),
    InstrumentInfo("FIL/USDT", "crypto", "FIL", "USDT", "FILUSDT"),
)

_INTERVAL_MAP = {tf: tf for tf in SUPPORTED_TIMEFRAMES}


class BinanceSpotProvider:
    code = "binance_spot"

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "private-trading-ai/0.1"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self.client.get("/api/v3/ping")
            latency = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                return ProviderHealth(
                    provider_code=self.code,
                    ok=False,
                    latency_ms=latency,
                    message=f"ping_status={response.status_code}",
                    degraded=True,
                )
            return ProviderHealth(
                provider_code=self.code,
                ok=True,
                latency_ms=latency,
                message="ok",
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                provider_code=self.code,
                ok=False,
                message=str(exc),
                degraded=True,
            )

    async def list_instruments(self) -> list[InstrumentInfo]:
        return list(DEFAULT_SYMBOLS)

    async def fetch_candles(
        self,
        *,
        provider_symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedCandle]:
        if timeframe not in _INTERVAL_MAP:
            raise AppError(
                "UNSUPPORTED_TIMEFRAME",
                f"Timeframe {timeframe!r} not supported by {self.code}",
                retryable=False,
            )
        params: dict[str, object] = {
            "symbol": provider_symbol.upper(),
            "interval": _INTERVAL_MAP[timeframe],
            "limit": max(1, min(limit, 1000)),
        }
        if start is not None:
            params["startTime"] = int(start.astimezone(UTC).timestamp() * 1000)
        if end is not None:
            params["endTime"] = int(end.astimezone(UTC).timestamp() * 1000)

        try:
            response = await self.client.get("/api/v3/klines", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "PROVIDER_HTTP_ERROR",
                f"Binance klines failed: {exc.response.status_code}",
                retryable=exc.response.status_code >= 500,
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "PROVIDER_UNAVAILABLE",
                "Binance request failed",
                retryable=True,
            ) from exc

        rows = response.json()
        if not isinstance(rows, list):
            raise AppError("PROVIDER_BAD_PAYLOAD", "Unexpected klines payload", retryable=False)

        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        candles: list[NormalizedCandle] = []
        for row in rows:
            open_ms = int(row[0])
            close_ms = int(row[6])
            candles.append(
                NormalizedCandle(
                    open_time=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                    is_final=close_ms <= now_ms,
                    provider_symbol=provider_symbol.upper(),
                    timeframe=timeframe,
                )
            )
        candles.sort(key=lambda c: c.open_time)
        return candles
