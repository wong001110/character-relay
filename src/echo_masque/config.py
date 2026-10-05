"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from echo_masque import __version__
from echo_masque.mcp_config import McpProviderConfig
from echo_masque.target_endpoint_policy import (
    DEFAULT_PROVIDER_ALLOWED_ORIGINS,
    validated_operator_origin,
)

LangGraphMode = Literal["off", "condition_watch", "character_turn", "social_turn"]
LangGraphWorkflow = Literal["condition_watch", "character_turn", "social_turn"]
KnowledgeObjectStorageProvider = Literal["cloudflare_r2", "aws_s3", "local_filesystem"]
_LANGGRAPH_MODE_RANK: dict[str, int] = {
    "off": 0,
    "condition_watch": 1,
    "character_turn": 2,
    "social_turn": 3,
}


class Settings(BaseSettings):
    """Environment-derived settings with credential-free defaults."""

    model_config = SettingsConfigDict(
        env_prefix="CHARACTER_RELAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Character Relay"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "sqlite:///./echo_masque.db"
    provider_trace_retention_days: int = 7
    provider_trace_max_records: int = 2000
    # Production egress is origin-admitted before configurable target/provider clients send.
    # Operator entries are exact credential-free HTTPS origins, supplied as a comma-separated
    # CHARACTER_RELAY_* value.  The known provider origins cover the existing non-custom presets.
    provider_allowed_origins: Annotated[tuple[str, ...], NoDecode] = (
        DEFAULT_PROVIDER_ALLOWED_ORIGINS
    )
    http_target_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()
    knowledge_external_sync_report_retention_days: int = Field(default=7, ge=1, le=90)
    # Knowledge Fabric acquisition and derived-work maintenance are intentionally not part of
    # the HTTP API's default lifecycle. Run them through ``knowledge_fabric_worker`` instead so
    # a large crawl cannot consume the request process's thread or PID budget. This temporary
    # API-side switch exists only for a controlled migration/recovery and must stay opt-in.
    knowledge_fabric_api_background_workers_enabled: bool = False
    api_thread_pool_limit: int = Field(default=16, ge=1, le=40)
    mcp_providers: tuple[McpProviderConfig, ...] = ()
    turn_job_max_queue: int = Field(default=20, ge=1, le=200)
    turn_job_max_concurrency: int = Field(default=2, ge=1, le=16)
    turn_job_deadline_seconds: int = Field(default=300, ge=30, le=900)
    turn_job_retention_hours: int = Field(default=24, ge=1, le=168)

    langgraph_mode: LangGraphMode = "off"

    # Cloudflare R2 is the production default.  The service talks only through the
    # private S3-compatible API so an explicitly configured AWS S3 deployment can
    # use the same boundary later.  A private filesystem is an explicit single-node,
    # mounted-volume option; without its provider and absolute root, ingestion fails
    # cleanly when invoked.
    knowledge_object_storage_provider: KnowledgeObjectStorageProvider = "cloudflare_r2"
    knowledge_object_storage_endpoint: str | None = None
    knowledge_object_storage_bucket: str | None = None
    knowledge_object_storage_region: str | None = None
    knowledge_object_storage_access_key_id: SecretStr | None = None
    knowledge_object_storage_secret_access_key: SecretStr | None = None
    knowledge_object_storage_prefix: str = "knowledge-fabric"
    knowledge_object_storage_filesystem_path: str | None = None

    browser_tools_enabled: bool = True
    browser_page_idle_seconds: int = 180
    browser_context_idle_seconds: int = 300
    browser_idle_seconds: int = 600
    browser_max_lifetime_seconds: int = 3600
    browser_max_operations: int = 100
    browser_max_concurrent_contexts: int = 3
    browser_navigation_timeout_ms: int = 15_000

    scheduler_poll_seconds: int = 5
    scheduler_retry_seconds: int = 30
    scheduler_max_attempts: int = 3
    condition_watch_poll_seconds: int = 60

    discord_tool_bot_token: SecretStr | None = Field(
        default=None,
        validation_alias="DISCORD_BOT_TOKEN",
    )

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
    cli_auth_enabled: bool = False
    cli_auth_public_origin: str = "https://echo-masque-production.up.railway.app"
    cli_device_ttl_seconds: int = Field(default=600, ge=1, le=600)
    cli_access_ttl_seconds: int = Field(default=900, ge=1, le=900)
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

    @field_validator("cli_auth_public_origin")
    @classmethod
    def cli_origin_is_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        ):
            raise ValueError("CLI approval origin must be a credential-free HTTPS origin.")
        return value.rstrip("/")

    @field_validator("knowledge_object_storage_endpoint")
    @classmethod
    def object_storage_endpoint_is_private_s3_api(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Knowledge object-storage endpoint must be a credential-free HTTPS URL."
            )
        return value.rstrip("/")

    @field_validator("provider_allowed_origins", "http_target_allowed_origins", mode="before")
    @classmethod
    def outbound_origins_are_exact_https_entries(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            values = tuple(item for item in value.split(",") if item.strip())
        elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            values = tuple(value)
        else:
            raise ValueError("Allowed outbound origins must be comma-separated HTTPS origins.")
        return tuple(dict.fromkeys(validated_operator_origin(item) for item in values))

    @field_validator("knowledge_object_storage_bucket", "knowledge_object_storage_prefix")
    @classmethod
    def object_storage_names_are_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Knowledge object-storage names must not be blank.")
        return value

    @field_validator("knowledge_object_storage_filesystem_path")
    @classmethod
    def object_storage_filesystem_path_is_absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("Knowledge filesystem storage path must be absolute.")
        return str(path)

    def langgraph_allows(self, workflow: LangGraphWorkflow) -> bool:
        """Return whether the cumulative rollout mode includes a workflow."""

        return _LANGGRAPH_MODE_RANK[self.langgraph_mode] >= _LANGGRAPH_MODE_RANK[workflow]


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings with process-local memoization."""

    return Settings()
