from fastapi.testclient import TestClient
from private_trading_api.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "private-trading-ai"
    assert "X-Correlation-ID" in response.headers


def test_v1_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
