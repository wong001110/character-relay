"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_masque import __version__

LangGraphMode = Literal["off", "condition_watch", "character_turn", "social_turn"]
LangGraphWorkflow = Literal["condition_watch", "character_turn", "social_turn"]
CharacterTurnIntelligenceMode = Literal["off", "shadow", "active"]
ConversationIntelligenceRolloutMode = Literal["off", "shadow", "active"]
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

    langgraph_mode: LangGraphMode = "off"
    turn_intelligence_character_context_mode: CharacterTurnIntelligenceMode = "off"
    smart_participation_v4_graph_rerank_mode: ConversationIntelligenceRolloutMode = "shadow"
    smart_participation_v4_learned_state_mode: ConversationIntelligenceRolloutMode = "shadow"
    smart_participation_v4_speaker_mode: ConversationIntelligenceRolloutMode = "shadow"
    smart_participation_v4_utility_mode: ConversationIntelligenceRolloutMode = "shadow"
    conversation_planner_mode: ConversationIntelligenceRolloutMode = "shadow"
    conversation_planner_rollout_percent: int = Field(default=0, ge=0, le=100)

    semantic_embedding_enabled: bool = False
    semantic_embedding_model: str = "intfloat/multilingual-e5-small"
    semantic_embedding_model_file: str = "onnx/model_O4.onnx"
    semantic_embedding_dimension: int = 384
    semantic_embedding_cache_dir: str = "./.cache/character-relay/embeddings"
    knowledge_semantic_retrieval_enabled: bool = True
    media_semantic_recall_enabled: bool = True
    expression_semantic_retrieval_enabled: bool = True
    semantic_participation_enabled: bool = False

    # Public Character Discovery source configuration. YouTube works without a credential via
    # metadata-only yt-dlp search; an optional Data API key upgrades acquisition to the official
    # API. Bilibili remains experimental but is available by default without environment setup.
    youtube_data_api_key: SecretStr | None = None
    youtube_discovery_search_cache_seconds: int = Field(default=4 * 60 * 60, ge=300, le=86400)
    youtube_discovery_popular_cache_seconds: int = Field(default=60 * 60, ge=300, le=86400)
    youtube_discovery_max_search_queries_per_session: int = Field(default=2, ge=0, le=5)
    bilibili_discovery_experimental_enabled: bool = True
    bilibili_discovery_search_cache_seconds: int = Field(default=4 * 60 * 60, ge=300, le=86400)
    bilibili_discovery_max_search_queries_per_session: int = Field(default=1, ge=0, le=3)
    bilibili_discovery_max_results_per_query: int = Field(default=6, ge=1, le=12)

    # Complete Discovery Runtime remains independently kill-switchable. Media inspection reuses
    # the existing Key Group + MediaAnalysis runtime; AUTO has an additional hard global switch.
    discovery_complete_runtime_enabled: bool = True
    discovery_media_inspection_enabled: bool = True
    discovery_auto_share_global_enabled: bool = False

    # Deployment Activity Runtime. Stable hashing chooses whether a bounded daily leisure session
    # occurs, its platform/time/duration, and persisted sessions survive process restarts.
    discovery_activity_poll_seconds: int = Field(default=60, ge=10, le=1800)
    discovery_activity_session_probability_percent: int = Field(default=70, ge=0, le=100)
    discovery_activity_window_start_minute: int = Field(default=10 * 60, ge=0, le=1439)
    discovery_activity_window_end_minute: int = Field(default=23 * 60, ge=1, le=1440)
    discovery_activity_duration_min_minutes: int = Field(default=12, ge=5, le=120)
    discovery_activity_duration_max_minutes: int = Field(default=30, ge=5, le=180)
    discovery_activity_latest_start_delay_minutes: int = Field(default=90, ge=5, le=240)
    discovery_activity_candidate_budget: int = Field(default=12, ge=3, le=30)
    discovery_activity_open_budget: int = Field(default=3, ge=0, le=10)
    discovery_activity_watch_budget: int = Field(default=1, ge=0, le=5)
    discovery_activity_exploration_percent: int = Field(default=20, ge=0, le=100)

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
        """Enable shared embeddings lazily in production and through explicit feature flags."""

        return (
            self.environment == "production"
            or self.semantic_embedding_enabled
            or self.semantic_participation_enabled
        )


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings with process-local memoization."""

    return Settings()
