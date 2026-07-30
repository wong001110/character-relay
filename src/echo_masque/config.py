"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
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

    # Legacy environment credentials remain read-only migration fallbacks. Admin API access
    # is role-based and never trusts the legacy token after Phase 15C.
    admin_token: SecretStr | None = None
    adaptive_api_key: SecretStr | None = None
    judge_api_key: SecretStr | None = None

    auth_cookie_name: str = "echo_masque_session"
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 30
    auth_cookie_secure: bool = False
    public_registration_enabled: bool = False
    legacy_local_user_enabled: bool = True
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_display_name: str = "Echo Masque Admin"
    credential_encryption_keys: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings."""

    return Settings()
