"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_masque import __version__


class Settings(BaseSettings):
    """Environment-derived settings with credential-free defaults."""

    # The ECHO_MASQUE_ prefix remains a compatibility contract for existing Railway
    # deployments while the user-facing product transitions to Character Relay.
    model_config = SettingsConfigDict(
        env_prefix="ECHO_MASQUE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Character Relay"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "sqlite:///./echo_masque.db"
    provider_trace_retention_days: int = 7
    provider_trace_max_records: int = 2000

    # Smart Participation V3 semantic relevance. Production explicitly enables this so
    # tests and source checkouts never download a model merely by creating a Character Card.
    semantic_participation_enabled: bool = False
    semantic_embedding_model: str = "intfloat/multilingual-e5-small"
    semantic_embedding_model_file: str = "onnx/model_O4.onnx"
    semantic_embedding_dimension: int = 384
    semantic_embedding_cache_dir: str = "./.cache/character-relay/embeddings"

    # Browser Capability. Chromium launches lazily on first use, stays warm briefly for
    # repeated search/read calls, then closes automatically when idle or after hard limits.
    browser_tools_enabled: bool = True
    browser_page_idle_seconds: int = 180
    browser_context_idle_seconds: int = 300
    browser_idle_seconds: int = 600
    browser_max_lifetime_seconds: int = 3600
    browser_max_operations: int = 100
    browser_max_concurrent_contexts: int = 3
    browser_navigation_timeout_ms: int = 15_000

    # V1.2 reminder delivery. Reminders are persisted in SQLite and delivered later using
    # the deployment's Discord webhook identity (or the managed Bot identity when selected).
    scheduler_poll_seconds: int = 5
    scheduler_retry_seconds: int = 30
    scheduler_max_attempts: int = 3

    # Discord read/write/file Tools use the same managed Bot credential name as the
    # Discord Connector. The former ECHO_MASQUE_DISCORD_TOOL_BOT_TOKEN name is accepted as
    # a migration fallback, but new deployments should use DISCORD_BOT_TOKEN everywhere.
    discord_tool_bot_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DISCORD_BOT_TOKEN",
            "ECHO_MASQUE_DISCORD_TOOL_BOT_TOKEN",
        ),
    )

    # Legacy environment credentials remain read-only migration fallbacks. Admin API access
    # is role-based and never trusts the legacy token after Phase 15C.
    admin_token: SecretStr | None = None
    adaptive_api_key: SecretStr | None = None
    judge_api_key: SecretStr | None = None
    authoring_api_key: SecretStr | None = None
    connector_shared_secret: SecretStr | None = None

    auth_cookie_name: str = "echo_masque_session"
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 30
    auth_cookie_secure: bool = False
    public_registration_enabled: bool = False
    legacy_local_user_enabled: bool = True
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_display_name: str = "Character Relay Admin"
    public_demo_enabled: bool = False
    public_demo_max_runs_per_day: int = 20
    credential_encryption_keys: SecretStr | None = None

    request_limit_per_minute: int = 300
    login_failure_limit: int = 5
    login_failure_window_seconds: int = 15 * 60
    login_block_seconds: int = 15 * 60
    max_characters_per_user: int = 100
    max_scenarios_per_user: int = 250
    max_test_packs_per_user: int = 100
    max_runs_per_user: int = 2000
    max_matrices_per_user: int = 100
    max_matrix_tasks_per_day: int = 1000
    max_concurrent_runs_per_user: int = 3
    max_matrix_concurrency_per_user: int = 4
    max_workspace_records_per_user: int = 3000
    max_authoring_generations_per_day: int = 50
    max_evaluation_cases_per_day: int = 1000
    max_template_instantiations_per_day: int = 100
    max_shared_assets_per_bundle: int = 200


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings."""

    return Settings()
