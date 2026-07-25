"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_masque import __version__


class Settings(BaseSettings):
    """Environment-derived settings with credential-free defaults."""

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
    database_url: str = "sqlite:///./echo_masque.db"


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings."""

    return Settings()
