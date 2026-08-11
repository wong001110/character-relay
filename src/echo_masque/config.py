"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_masque import __version__

LangGraphMode = Literal["off", "condition_watch", "character_turn", "social_turn"]
LangGraphWorkflow = Literal["condition_watch", "character_turn", "social_turn"]
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
    )

    app_name: str = "Character Relay"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "sqlite:///./echo_masque.db"
    provider_trace_retention_days: int = 7
    provider_trace_max_records: int = 2000

    # One cumulative rollout value controls LangGraph adoption. Moving forward through the
    # modes keeps already-migrated workflows enabled; "off" is the global rollback state.
    langgraph_mode: LangGraphMode = "off"

    # Shared semantic embedding runtime. semantic_embedding_enabled allows Knowledge RAG and
    # Media Recall to use the same local multilingual E5 model without requiring Smart
    # Participation itself to be enabled. Existing deployments that already enable semantic
    # participation also keep the shared embedding runtime available for backward compatibility.
    semantic_embedding_enabled: bool = False
    semantic_embedding_model: str = "intfloat/multilingual-e5-small"
    semantic_embedding_model_file: str = "onnx/model_O4.onnx"
    semantic_embedding_dimension: int = 384
    semantic_embedding_cache_dir: str = "./.cache/character-relay/embeddings"
    knowledge_semantic_retrieval_enabled: bool = True
    media_semantic_recall_enabled: bool = True

    # Smart Participation V3 semantic relevance. Production explicitly enables this so
    # tests and source checkouts never download a model merely by creating a Character Card.
    semantic_participation_enabled: bool = False

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

    # V2 condition watches are intentionally lower-frequency than reminder delivery. Each
    # individual watch also enforces a minimum 5-minute evaluation cadence in Runtime.
    condition_watch_poll_seconds: int = 60

    # Discord read/write/file Tools use the same managed Bot credential name as the
    # Discord Connector. DISCORD_BOT_TOKEN is intentionally shared between services.
    discord_tool_bot_token: SecretStr | None = Field(
        default=None,
        validation_alias="DISCORD_BOT_TOKEN",
    )

    # Environment credentials remain optional runtime fallbacks. Admin API access is
    # role-based and never trusts a shared token in place of authenticated authorization.
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

    def langgraph_allows(self, workflow: LangGraphWorkflow) -> bool:
        """Return whether the cumulative rollout mode includes a workflow."""

        return _LANGGRAPH_MODE_RANK[self.langgraph_mode] >= _LANGGRAPH_MODE_RANK[workflow]

    @property
    def semantic_embedding_runtime_enabled(self) -> bool:
        """Keep old semantic-participation deployments compatible with shared embeddings."""

        return self.semantic_embedding_enabled or self.semantic_participation_enabled


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings."""

    return Settings()
