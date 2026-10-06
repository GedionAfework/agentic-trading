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

    ollama_base_url: str = "http://localhost:11434"
    main_model: str = "qwen2.5:14b"
    embedding_model: str = "nomic-embed-text"

    jwt_secret: str = Field(
        default="dev-only-change-me",
        description="JWT signing secret — must be overridden in production",
    )
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    scanner_enabled: bool = True
    notifications_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
