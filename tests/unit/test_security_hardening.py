from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from private_trading_api.main import create_app
from private_trading_api.rate_limit import limiter
from private_trading_core.config import Settings, production_settings_errors
from private_trading_core.security import scan_text_for_secrets


def test_production_rejects_insecure_defaults() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="dev-only-change-me",
        database_url="postgresql+asyncpg://trading:trading@db/trading",
        object_storage_secret_key="test",
    )
    errors = production_settings_errors(settings)
    assert any("jwt_secret" in e for e in errors)
    assert any("database_url" in e for e in errors)
    assert any("object_storage_secret_key" in e for e in errors)


def test_production_accepts_strong_secrets() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="x" * 32,
        database_url="postgresql+asyncpg://app:s3curePass@db/trading",
        object_storage_secret_key="prod-object-storage-credential",
        allow_insecure_defaults=False,
    )
    assert production_settings_errors(settings) == []


def test_development_skips_production_guard() -> None:
    settings = Settings(app_env="development", jwt_secret="dev-only-change-me")
    assert production_settings_errors(settings) == []


def test_secret_scan_finds_aws_key() -> None:
    findings = scan_text_for_secrets("aws_access_key_id = AKIAIOSFODNN7EXAMPLE")
    # EXAMPLE substring is filtered
    assert findings == []
    # AKIA + 16 uppercase/digit chars
    findings = scan_text_for_secrets("aws_access_key_id = AKIAIOSFODNN7ABCDE12")
    assert any(f["rule"] == "aws_access_key" for f in findings)


def test_metrics_endpoint_renders() -> None:
    limiter.reset()
    client = TestClient(create_app())
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "pta_http_requests_total" in response.text
    assert "pta_process_uptime_seconds" in response.text


def test_metrics_bearer_required_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "metrics-secret-token")
    # Settings are cached — clear cache
    from private_trading_core.config import get_settings

    get_settings.cache_clear()
    try:
        limiter.reset()
        client = TestClient(create_app())
        denied = client.get("/metrics")
        assert denied.status_code == 401
        ok = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret-token"})
        assert ok.status_code == 200
    finally:
        monkeypatch.delenv("METRICS_BEARER_TOKEN", raising=False)
        get_settings.cache_clear()


def test_rate_limit_on_auth_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_AUTH_REQUESTS", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    from private_trading_core.config import get_settings

    get_settings.cache_clear()
    limiter.reset()
    try:
        client = TestClient(create_app())
        # Login will 401/422 without DB user — still counts toward limiter
        statuses = []
        for _ in range(5):
            res = client.post("/v1/auth/login", json={"email": "a@b.c", "password": "x"})
            statuses.append(res.status_code)
        assert 429 in statuses
        assert client.get("/health").status_code == 200  # health exempt
    finally:
        monkeypatch.delenv("RATE_LIMIT_AUTH_REQUESTS", raising=False)
        monkeypatch.delenv("RATE_LIMIT_WINDOW_SECONDS", raising=False)
        get_settings.cache_clear()
        limiter.reset()


def test_upload_content_length_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    from private_trading_core.config import get_settings

    get_settings.cache_clear()
    limiter.reset()
    try:
        client = TestClient(create_app())
        # Unauthenticated — middleware runs before auth
        res = client.post(
            "/v1/vision/screenshots",
            headers={"Content-Length": "99999"},
            content=b"x",
        )
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "UPLOAD_TOO_LARGE"
    finally:
        monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
        get_settings.cache_clear()
        limiter.reset()


def test_boot_guard_matches_lifespan_policy() -> None:
    """Lifespan calls production_settings_errors and SystemExits when non-empty."""
    bad = Settings(
        app_env="production",
        jwt_secret="dev-only-change-me",
        database_url="postgresql+asyncpg://trading:trading@db/trading",
        object_storage_secret_key="test",
    )
    assert production_settings_errors(bad)
    good = Settings(
        app_env="production",
        jwt_secret="y" * 32,
        database_url="postgresql+asyncpg://app:s3curePass@db/trading",
        object_storage_secret_key="prod-object-storage-credential",
    )
    assert production_settings_errors(good) == []
