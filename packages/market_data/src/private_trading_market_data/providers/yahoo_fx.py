"""Free forex OHLC via Yahoo Finance public chart API (research / backtest use).

Volume is often zero on FX — stored as 0 with no invented liquidity. Not a
licensed institutional feed; Gate B / FX volume-harmony remain open decisions.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from private_trading_core.errors import AppError

from private_trading_market_data.contracts import (
    SUPPORTED_TIMEFRAMES,
    InstrumentInfo,
    NormalizedCandle,
    ProviderHealth,
)

# Yahoo symbols for major + liquid cross spot FX (free research OHLC)
DEFAULT_FX_SYMBOLS: tuple[InstrumentInfo, ...] = (
    InstrumentInfo("EUR/USD", "forex", "EUR", "USD", "EURUSD=X"),
    InstrumentInfo("GBP/USD", "forex", "GBP", "USD", "GBPUSD=X"),
    InstrumentInfo("USD/JPY", "forex", "USD", "JPY", "USDJPY=X"),
    InstrumentInfo("USD/CHF", "forex", "USD", "CHF", "USDCHF=X"),
    InstrumentInfo("AUD/USD", "forex", "AUD", "USD", "AUDUSD=X"),
    InstrumentInfo("USD/CAD", "forex", "USD", "CAD", "USDCAD=X"),
    InstrumentInfo("NZD/USD", "forex", "NZD", "USD", "NZDUSD=X"),
    InstrumentInfo("EUR/GBP", "forex", "EUR", "GBP", "EURGBP=X"),
    InstrumentInfo("EUR/JPY", "forex", "EUR", "JPY", "EURJPY=X"),
    InstrumentInfo("GBP/JPY", "forex", "GBP", "JPY", "GBPJPY=X"),
    InstrumentInfo("AUD/JPY", "forex", "AUD", "JPY", "AUDJPY=X"),
    InstrumentInfo("EUR/AUD", "forex", "EUR", "AUD", "EURAUD=X"),
    InstrumentInfo("EUR/CHF", "forex", "EUR", "CHF", "EURCHF=X"),
    InstrumentInfo("GBP/CHF", "forex", "GBP", "CHF", "GBPCHF=X"),
    InstrumentInfo("AUD/NZD", "forex", "AUD", "NZD", "AUDNZD=X"),
    InstrumentInfo("GBP/AUD", "forex", "GBP", "AUD", "GBPAUD=X"),
)

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m",
    "4h": "60m",  # Yahoo has no native 4h; caller should prefer 1h/1d for FX
    "1d": "1d",
}

# Yahoo 422s if period1 is older than the interval's available window.
_MAX_LOOKBACK_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "1h": 730,
    "4h": 730,
}


class YahooFxProvider:
    code = "yahoo_fx"

    def __init__(
        self,
        *,
        base_url: str = "https://query1.finance.yahoo.com",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={
                "User-Agent": "private-trading-ai/0.1 (research backfill)",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self.client.get(
                "/v8/finance/chart/EURUSD=X",
                params={"range": "5d", "interval": "1d"},
            )
            latency = (time.perf_counter() - started) * 1000
            ok = response.status_code == 200
            return ProviderHealth(
                provider_code=self.code,
                ok=ok,
                latency_ms=latency,
                message="ok" if ok else f"status={response.status_code}",
                degraded=not ok,
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                provider_code=self.code,
                ok=False,
                message=str(exc),
                degraded=True,
            )

    async def list_instruments(self) -> list[InstrumentInfo]:
        return list(DEFAULT_FX_SYMBOLS)

    async def fetch_candles(
        self,
        *,
        provider_symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NormalizedCandle]:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise AppError(
                "UNSUPPORTED_TIMEFRAME",
                f"Timeframe {timeframe!r} not supported by {self.code}",
                retryable=False,
            )
        interval = _INTERVAL_MAP[timeframe]
        now = datetime.now(UTC)
        period2_dt = end.astimezone(UTC) if end is not None else now
        max_days = _MAX_LOOKBACK_DAYS.get(timeframe)
        floor = period2_dt - timedelta(days=max_days) if max_days else datetime(1970, 1, 1, tzinfo=UTC)
        start_dt = start.astimezone(UTC) if start is not None else floor
        if start_dt < floor:
            start_dt = floor
        period1 = int(start_dt.timestamp())
        period2 = int(period2_dt.timestamp())

        try:
            response = await self.client.get(
                f"/v8/finance/chart/{provider_symbol}",
                params={
                    "period1": period1,
                    "period2": period2,
                    "interval": interval,
                    "includePrePost": "false",
                    "events": "div,splits",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "PROVIDER_HTTP_ERROR",
                f"Yahoo FX chart failed: {exc.response.status_code}",
                retryable=exc.response.status_code >= 500,
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "PROVIDER_UNAVAILABLE",
                "Yahoo FX request failed",
                retryable=True,
            ) from exc

        payload = response.json()
        try:
            result = payload["chart"]["result"][0]
            ts_list = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError(
                "PROVIDER_BAD_PAYLOAD",
                "Unexpected Yahoo FX payload",
                retryable=False,
            ) from exc

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        candles: list[NormalizedCandle] = []
        for i, ts in enumerate(ts_list):
            o, h, low, c = (
                opens[i] if i < len(opens) else None,
                highs[i] if i < len(highs) else None,
                lows[i] if i < len(lows) else None,
                closes[i] if i < len(closes) else None,
            )
            if o is None or h is None or low is None or c is None:
                continue
            vol_raw = volumes[i] if i < len(volumes) else None
            volume = Decimal("0") if vol_raw is None else Decimal(str(vol_raw))
            open_time = datetime.fromtimestamp(int(ts), tz=UTC)
            candles.append(
                NormalizedCandle(
                    open_time=open_time,
                    open=Decimal(str(o)),
                    high=Decimal(str(h)),
                    low=Decimal(str(low)),
                    close=Decimal(str(c)),
                    volume=volume,
                    is_final=open_time < now,
                    provider_symbol=provider_symbol,
                    timeframe=timeframe,
                )
            )
        candles.sort(key=lambda c: c.open_time)
        if limit and start is None and end is None and len(candles) > limit:
            candles = candles[-limit:]
        return candles
