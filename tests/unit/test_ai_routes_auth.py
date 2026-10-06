from __future__ import annotations

from fastapi.testclient import TestClient
from private_trading_api.main import create_app
from private_trading_core.config import get_settings


def test_ai_health_requires_auth() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/v1/ai/health")
    assert response.status_code == 401
