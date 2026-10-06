from __future__ import annotations

import json

import httpx
import pytest
import respx
from private_trading_ai_gateway.circuit_breaker import CircuitBreaker
from private_trading_ai_gateway.client import AIGateway, AIGatewayError
from private_trading_ai_gateway.redaction import redact_text
from private_trading_core.config import Settings
from pydantic import BaseModel


class TinyOut(BaseModel):
    ok: bool
    echo: str


def test_redact_secrets() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    text = f"Authorization: Bearer {jwt} api_key=supersecret"
    redacted = redact_text(text)
    assert "supersecret" not in redacted
    assert jwt not in redacted
    assert "[REDACTED]" in redacted


def test_circuit_breaker_opens() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.allow()
    breaker.record_failure()
    assert not breaker.allow()
    assert breaker.state == "open"


@pytest.mark.asyncio
@respx.mock
async def test_structured_chat_repairs_once() -> None:
    settings = Settings(
        ollama_base_url="http://ollama.test",
        main_model="test-model",
        ai_max_retries=1,
    )
    route = respx.post("http://ollama.test/api/chat")
    route.side_effect = [
        httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "{not-json"}},
        ),
        httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"ok": True, "echo": "hi"}),
                }
            },
        ),
    ]

    async with AIGateway(settings) as gateway:
        result, meta = await gateway.structured_chat(
            messages=[{"role": "user", "content": "smoke"}],
            schema=TinyOut,
        )

    assert result.ok is True
    assert result.echo == "hi"
    assert meta["repaired"] is True
    assert meta["attempts"] == 2
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_structured_chat_fails_closed_after_repair() -> None:
    settings = Settings(
        ollama_base_url="http://ollama.test",
        main_model="test-model",
        ai_max_retries=1,
    )
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "{bad"}},
        )
    )

    async with AIGateway(settings) as gateway:
        with pytest.raises(AIGatewayError) as exc:
            await gateway.structured_chat(
                messages=[{"role": "user", "content": "smoke"}],
                schema=TinyOut,
            )
    assert exc.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_embed_uses_api_embed() -> None:
    settings = Settings(
        ollama_base_url="http://ollama.test",
        embedding_model="nomic-embed-text",
        ai_max_retries=1,
    )
    respx.post("http://ollama.test/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    )

    async with AIGateway(settings) as gateway:
        vector = await gateway.embed("hello")

    assert vector == [0.1, 0.2, 0.3]
