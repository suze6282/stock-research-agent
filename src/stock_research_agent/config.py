import math
import os
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

_REDACTED_VALUE = "***"
_SUPPORTED_DATABASE_DRIVERS = frozenset({"postgresql", "postgresql+psycopg"})


def _default_blob_storage_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "stock-research-agent" / "blobs"
    return Path.home() / ".local" / "share" / "stock-research-agent" / "blobs"


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ProviderNetworkMode(StrEnum):
    OFFLINE = "OFFLINE"
    LIVE = "LIVE"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "stock-research-agent"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str | None = None
    database_echo: bool = False
    api_prefix: str = "/api/v1"
    provider_network_enabled: bool = False
    provider_network_mode: ProviderNetworkMode = ProviderNetworkMode.OFFLINE
    provider_connect_timeout_seconds: float = 5.0
    provider_read_timeout_seconds: float = 15.0
    provider_total_timeout_seconds: float = 30.0
    provider_max_response_bytes: int = 5_242_880
    provider_max_redirects: int = 3
    provider_max_attempts: int = 3
    provider_retry_base_delay_seconds: float = 0.25
    provider_rate_limit_per_second: float = 1.0
    provider_user_agent: str = "stock-research-agent/0.1 (offline-default)"
    blob_storage_root: Path = _default_blob_storage_root()
    document_max_bytes: int = Field(default=10_000_000, ge=1, le=10_000_000)
    document_max_pdf_pages: int = Field(default=500, ge=1, le=500)
    document_max_characters: int = Field(default=5_000_000, ge=1, le=5_000_000)
    rag_query_max_characters: int = Field(default=256, ge=1, le=256)
    rag_max_results: int = Field(default=20, ge=1, le=20)
    rag_production_embedding_enabled: bool = False

    @field_validator("app_port")
    @classmethod
    def validate_app_port(cls, value: int) -> int:
        if not 1 <= value <= 65_535:
            raise ValueError("APP_PORT must be between 1 and 65535")
        return value

    @field_validator(
        "provider_connect_timeout_seconds",
        "provider_read_timeout_seconds",
        "provider_total_timeout_seconds",
        "provider_retry_base_delay_seconds",
        "provider_rate_limit_per_second",
    )
    @classmethod
    def validate_provider_positive_finite_value(cls, value: float) -> float:
        if value <= 0 or not math.isfinite(value):
            raise ValueError("Provider time and rate settings must be positive and finite")
        return value

    @field_validator("provider_max_response_bytes")
    @classmethod
    def validate_provider_max_response_bytes(cls, value: int) -> int:
        if not 1 <= value <= 52_428_800:
            raise ValueError("PROVIDER_MAX_RESPONSE_BYTES must be between 1 and 52428800")
        return value

    @field_validator("provider_max_redirects")
    @classmethod
    def validate_provider_max_redirects(cls, value: int) -> int:
        if not 0 <= value <= 5:
            raise ValueError("PROVIDER_MAX_REDIRECTS must be between 0 and 5")
        return value

    @field_validator("provider_max_attempts")
    @classmethod
    def validate_provider_max_attempts(cls, value: int) -> int:
        if not 1 <= value <= 3:
            raise ValueError("PROVIDER_MAX_ATTEMPTS must be between 1 and 3")
        return value

    @field_validator("provider_user_agent")
    @classmethod
    def validate_provider_user_agent(cls, value: str) -> str:
        if not 1 <= len(value) <= 256:
            raise ValueError("PROVIDER_USER_AGENT length must be between 1 and 256")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("PROVIDER_USER_AGENT must not contain control characters")
        return value

    @field_validator("blob_storage_root")
    @classmethod
    def validate_blob_storage_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("BLOB_STORAGE_ROOT must be an absolute path")
        if value == Path(value.anchor):
            raise ValueError("BLOB_STORAGE_ROOT must not be a filesystem root")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            url = make_url(value)
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from exc
        if url.drivername not in _SUPPORTED_DATABASE_DRIVERS:
            raise ValueError("DATABASE_URL uses an unsupported driver")
        return value

    @field_validator("rag_production_embedding_enabled")
    @classmethod
    def prevent_unconfigured_embedding(cls, value: bool) -> bool:
        if value:
            raise ValueError("production embedding provider is not configured in Stage 6")
        return value

    @model_validator(mode="after")
    def validate_environment_database(self) -> Self:
        if (
            self.provider_network_enabled
            and self.provider_network_mode is not ProviderNetworkMode.LIVE
        ):
            raise ValueError("PROVIDER_NETWORK_MODE must be LIVE when provider network is enabled")
        if self.app_env is AppEnvironment.PRODUCTION and self.database_url is None:
            raise ValueError("DATABASE_URL is required in production")

        if self.app_env is AppEnvironment.TEST and self.database_url is not None:
            database_name = make_url(self.database_url).database
            if database_name is None or not database_name.endswith("_test"):
                raise ValueError("Test DATABASE_URL database name must end with '_test'")

        return self

    def safe_summary(self) -> dict[str, object]:
        summary: dict[str, object] = self.model_dump(mode="json")
        summary["blob_storage_root"] = "<configured>"
        if self.database_url is not None:
            url = make_url(self.database_url)
            redacted_query: dict[str, str | tuple[str, ...]] = {
                key: (
                    tuple(_REDACTED_VALUE for _ in value)
                    if isinstance(value, tuple)
                    else _REDACTED_VALUE
                )
                for key, value in url.query.items()
            }
            summary["database_url"] = url.set(query=redacted_query).render_as_string(
                hide_password=True
            )
        return summary
