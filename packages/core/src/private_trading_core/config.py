from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "private-trading-ai"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://trading:trading@localhost:5433/trading",
        description="Async SQLAlchemy database URL",
    )
    redis_url: str = "redis://localhost:6380/0"

    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_access_key: str = "test"
    object_storage_secret_key: str = "test"
    object_storage_bucket: str = "private-trading"
    object_storage_region: str = "us-east-1"
    object_storage_local_root: str = "data/objects"

    ollama_base_url: str = "http://localhost:11434"
    # Prefer smaller tags for first smoke if VRAM is limited (e.g. qwen2.5:3b)
    main_model: str = "qwen2.5:7b"
    embedding_model: str = "nomic-embed-text"
    ai_timeout_seconds: float = 120.0
    ai_max_retries: int = 2
    ai_circuit_failure_threshold: int = 5
    ai_circuit_recovery_seconds: float = 30.0

    jwt_secret: str = Field(
        default="dev-only-change-me",
        description="JWT signing secret — must be overridden in production",
    )
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_bot_username: str = ""
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_link_ttl_seconds: int = 600

    scanner_enabled: bool = True
    notifications_enabled: bool = True

    # Public market data (no secrets required for Binance spot klines)
    binance_base_url: str = "https://api.binance.com"
    market_http_timeout_seconds: float = 20.0
    market_default_timeframes: str = "15m,1h"

    # Phase 19 — hardening
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_auth_requests: int = 20
    rate_limit_upload_requests: int = 10
    metrics_enabled: bool = True
    metrics_bearer_token: str = ""
    max_upload_bytes: int = 8 * 1024 * 1024
    allow_insecure_defaults: bool = False


_INSECURE_JWT_DEFAULTS = frozenset({"dev-only-change-me", "changeme", "secret", "test"})


def production_settings_errors(settings: Settings) -> list[str]:
    """Return blocking misconfigurations for production (Gate A)."""
    errors: list[str] = []
    if settings.app_env != "production":
        return errors
    if settings.allow_insecure_defaults:
        errors.append("allow_insecure_defaults must be false in production")
    secret = (settings.jwt_secret or "").strip()
    if not secret or secret.lower() in _INSECURE_JWT_DEFAULTS or len(secret) < 32:
        errors.append("jwt_secret must be a strong unique value (>=32 chars) in production")
    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        # Binding privately is fine; pointing at localhost hostname in k8s may be wrong —
        # warn-style: only flag default trading:trading credentials.
        pass
    if "trading:trading@" in settings.database_url:
        errors.append("database_url must not use the default trading:trading credentials")
    if settings.object_storage_secret_key in {"test", "minioadmin", ""}:
        errors.append("object_storage_secret_key must not use lab defaults in production")
    if settings.telegram_bot_token and not settings.telegram_webhook_secret:
        errors.append("telegram_webhook_secret required when telegram_bot_token is set")
    return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
