"""Minimal Telegram Bot API client with explicit 429 / transient / permanent error classes."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class TelegramError(Exception):
    def __init__(self, message: str, *, error_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class TelegramRateLimited(TelegramError):
    """HTTP 429 — Telegram tells us how long to wait."""

    def __init__(self, retry_after: int, message: str = "rate limited") -> None:
        super().__init__(message, error_code=429)
        self.retry_after = max(1, int(retry_after))


class TelegramTransientError(TelegramError):
    """5xx or network failure — safe to retry with backoff."""


class TelegramPermanentError(TelegramError):
    """4xx other than 429 (bad chat, blocked bot, bad markup) — do not retry."""


@dataclass(slots=True)
class SentMessage:
    message_id: int
    chat_id: int
    transport: str


class TelegramTransport(Protocol):
    configured: bool

    async def send_message(
        self, *, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> SentMessage: ...

    async def answer_callback_query(self, *, callback_query_id: str, text: str | None) -> None: ...

    async def download_file(self, file_id: str) -> bytes | None: ...

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]: ...

    async def set_webhook(self, *, url: str, secret_token: str) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


def webhook_authorized(header_value: str | None, configured_secret: str) -> bool:
    """Fail closed: no configured secret means no webhook is accepted."""
    if not configured_secret:
        return False
    return hmac.compare_digest((header_value or "").encode(), configured_secret.encode())


class TelegramClient:
    configured = True

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 15.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("telegram token is required")
        self._token = token
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=timeout_seconds)

    def _url(self, method: str) -> str:
        return f"{self._base}/bot{self._token}/{method}"

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(self._url(method), json=payload)
        except httpx.HTTPError as exc:
            raise TelegramTransientError(f"network: {type(exc).__name__}") from exc
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 429 or body.get("error_code") == 429:
            retry_after = int((body.get("parameters") or {}).get("retry_after") or 5)
            raise TelegramRateLimited(retry_after, str(body.get("description") or "429"))
        if response.status_code >= 500:
            raise TelegramTransientError(
                f"telegram {response.status_code}", error_code=response.status_code
            )
        if response.status_code >= 400 or not body.get("ok", False):
            raise TelegramPermanentError(
                str(body.get("description") or f"telegram {response.status_code}"),
                error_code=body.get("error_code") or response.status_code,
            )
        return body.get("result")

    async def send_message(
        self, *, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> SentMessage:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = await self._call("sendMessage", payload)
        return SentMessage(
            message_id=int(result["message_id"]), chat_id=chat_id, transport="telegram"
        )

    async def answer_callback_query(self, *, callback_query_id: str, text: str | None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        try:
            await self._call("answerCallbackQuery", payload)
        except TelegramPermanentError:
            # Expired callback ids are not worth failing the whole update over.
            return

    async def download_file(self, file_id: str) -> bytes | None:
        info = await self._call("getFile", {"file_id": file_id})
        path = (info or {}).get("file_path")
        if not path:
            return None
        url = f"{self._base}/file/bot{self._token}/{path}"
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise TelegramTransientError(f"network: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise TelegramPermanentError(f"file download {response.status_code}")
        return response.content

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload)
        return list(result or [])

    async def set_webhook(self, *, url: str, secret_token: str) -> dict[str, Any]:
        result = await self._call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        return {"ok": True, "result": result}

    async def aclose(self) -> None:
        await self._http.aclose()


@dataclass(slots=True)
class DryRunTelegramClient:
    """Used when no bot token is configured. Records outbound messages instead of sending."""

    configured: bool = False
    sent: list[dict[str, Any]] = field(default_factory=list)
    answered: list[dict[str, Any]] = field(default_factory=list)
    _next_id: int = 1

    async def send_message(
        self, *, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> SentMessage:
        message_id = self._next_id
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SentMessage(message_id=message_id, chat_id=chat_id, transport="dry_run")

    async def answer_callback_query(self, *, callback_query_id: str, text: str | None) -> None:
        self.answered.append({"callback_query_id": callback_query_id, "text": text})

    async def download_file(self, file_id: str) -> bytes | None:
        return None

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        return []

    async def set_webhook(self, *, url: str, secret_token: str) -> dict[str, Any]:
        return {"ok": False, "result": "bot token not configured"}

    async def aclose(self) -> None:
        return None


def build_client(
    *, token: str, base_url: str, timeout_seconds: float = 15.0
) -> TelegramClient | DryRunTelegramClient:
    if not token:
        return DryRunTelegramClient()
    return TelegramClient(token=token, base_url=base_url, timeout_seconds=timeout_seconds)
