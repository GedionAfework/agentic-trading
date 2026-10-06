from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from private_trading_core.config import Settings, get_settings
from private_trading_core.errors import AppError
from private_trading_core.logging import get_logger
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from private_trading_ai_gateway.circuit_breaker import CircuitBreaker
from private_trading_ai_gateway.redaction import redact_messages, redact_text

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIGatewayError(AppError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        details: dict | None = None,
    ) -> None:
        super().__init__(
            "AI_GATEWAY_ERROR",
            message,
            retryable=retryable,
            details=details or {},
        )


class AIGatewayUnavailable(AIGatewayError):
    def __init__(self, message: str = "AI inference is temporarily unavailable") -> None:
        super().__init__(message, retryable=True, details={"circuit": "open"})


class AIGateway:
    """Backend-only client for private Ollama-compatible inference."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.circuit = circuit_breaker or CircuitBreaker(
            failure_threshold=self.settings.ai_circuit_failure_threshold,
            recovery_seconds=self.settings.ai_circuit_recovery_seconds,
        )

    async def __aenter__(self) -> AIGateway:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.ollama_base_url.rstrip("/"),
                timeout=httpx.Timeout(self.settings.ai_timeout_seconds),
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise AIGatewayError("AIGateway client is not started", retryable=False)
        return self._client

    async def health(self) -> dict[str, Any]:
        if not self.circuit.allow():
            return {
                "status": "unavailable",
                "circuit": self.circuit.state,
                "endpoint": self.settings.ollama_base_url,
            }
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            models = [m.get("name") for m in response.json().get("models", [])]
            self.circuit.record_success()
            return {
                "status": "ok",
                "circuit": self.circuit.state,
                "endpoint": self.settings.ollama_base_url,
                "models": models,
                "main_model": self.settings.main_model,
                "embedding_model": self.settings.embedding_model,
            }
        except Exception as exc:  # noqa: BLE001
            self.circuit.record_failure()
            logger.warning("ai_health_failed err=%s", redact_text(str(exc)))
            return {
                "status": "down",
                "circuit": self.circuit.state,
                "endpoint": self.settings.ollama_base_url,
                "error": "inference_unreachable",
            }

    async def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        format_json: bool = False,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_circuit()
        payload = {
            "model": model or self.settings.main_model,
            "messages": redact_messages(messages),
            "stream": False,
        }
        if format_json:
            payload["format"] = "json"
        if options:
            payload["options"] = options

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.ai_max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self.client.post("/api/chat", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    self.circuit.record_success()
                    return data
                except httpx.HTTPStatusError as exc:
                    self.circuit.record_failure()
                    raise AIGatewayError(
                        "Inference request failed",
                        retryable=exc.response.status_code >= 500,
                        details={"status_code": exc.response.status_code},
                    ) from exc
                except (httpx.TransportError, httpx.TimeoutException):
                    self.circuit.record_failure()
                    raise

        raise AIGatewayError("Inference retries exhausted")

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self._ensure_circuit()
        payload = {
            "model": model or self.settings.embedding_model,
            "input": redact_text(text),
        }
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.ai_max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self.client.post("/api/embed", json=payload)
                    if response.status_code == 404:
                        # Older Ollama API
                        response = await self.client.post(
                            "/api/embeddings",
                            json={
                                "model": payload["model"],
                                "prompt": payload["input"],
                            },
                        )
                    response.raise_for_status()
                    data = response.json()
                    self.circuit.record_success()
                    if "embeddings" in data and data["embeddings"]:
                        return list(data["embeddings"][0])
                    if "embedding" in data:
                        return list(data["embedding"])
                    raise AIGatewayError("Unexpected embedding response shape", retryable=False)
                except httpx.HTTPStatusError as exc:
                    self.circuit.record_failure()
                    raise AIGatewayError(
                        "Embedding request failed",
                        retryable=exc.response.status_code >= 500,
                        details={"status_code": exc.response.status_code},
                    ) from exc
                except (httpx.TransportError, httpx.TimeoutException):
                    self.circuit.record_failure()
                    raise

        raise AIGatewayError("Embedding retries exhausted")

    async def structured_chat(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[T],
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> tuple[T, dict[str, Any]]:
        """Generate JSON, validate against schema, one constrained repair then fail closed."""
        schema_hint = json.dumps(schema.model_json_schema(), indent=2)
        first_messages = [
            *messages,
            {
                "role": "system",
                "content": (
                    "Respond with a single JSON object that matches this schema. "
                    f"No markdown.\n{schema_hint}"
                ),
            },
        ]
        raw = await self.chat(messages=first_messages, model=model, format_json=True)
        content = _message_content(raw)
        try:
            parsed = schema.model_validate_json(content)
            return parsed, {
                "attempts": 1,
                "repaired": False,
                "prompt_version": prompt_version,
                "model": model or self.settings.main_model,
            }
        except (ValidationError, json.JSONDecodeError) as first_err:
            repair_messages = [
                *first_messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your previous JSON was invalid for the schema. "
                        f"Error: {first_err}. Return corrected JSON only."
                    ),
                },
            ]
            repaired_raw = await self.chat(
                messages=repair_messages, model=model, format_json=True
            )
            repaired_content = _message_content(repaired_raw)
            try:
                parsed = schema.model_validate_json(repaired_content)
                return parsed, {
                    "attempts": 2,
                    "repaired": True,
                    "prompt_version": prompt_version,
                    "model": model or self.settings.main_model,
                }
            except (ValidationError, json.JSONDecodeError) as second_err:
                raise AIGatewayError(
                    "Structured output failed validation after repair",
                    retryable=False,
                    details={"error": str(second_err)},
                ) from second_err

    def _ensure_circuit(self) -> None:
        if not self.circuit.allow():
            raise AIGatewayUnavailable()


def _message_content(payload: dict[str, Any]) -> str:
    message = payload.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AIGatewayError("Empty model response", retryable=True)
    return content.strip()
