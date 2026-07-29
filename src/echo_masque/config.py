"""Application configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_masque import __version__

DEFAULT_SQLITE_URL = "sqlite:///./echo_masque.db"
RAILWAY_SQLITE_URL = "sqlite:////data/echo_masque.db"
RAILWAY_MARKERS = (
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_ID",
    "RAILWAY_DEPLOYMENT_ID",
    "RAILWAY_ENVIRONMENT_ID",
)


class Settings(BaseSettings):
    """Environment-derived settings with credential-free local defaults."""

    model_config = SettingsConfigDict(
        env_prefix="ECHO_MASQUE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Echo Masque"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = DEFAULT_SQLITE_URL
    admin_token: SecretStr | None = None
    adaptive_api_key: SecretStr | None = None
    judge_api_key: SecretStr | None = None


def resolve_platform_settings(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Force safe production defaults whenever Railway system variables are present."""

    source = environ if environ is not None else os.environ
    on_railway = any(source.get(name) for name in RAILWAY_MARKERS)
    if not on_railway:
        return settings

    updates: dict[str, object] = {"environment": "production"}
    if settings.database_url.startswith("sqlite"):
        updates["database_url"] = RAILWAY_SQLITE_URL
    return settings.model_copy(update=updates)


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings with platform safety normalization."""

    return resolve_platform_settings(Settings())
