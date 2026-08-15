from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch anchor missing: {path}\n{old[:160]}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, content: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if marker in text:
        return
    file.write_text(text.rstrip() + "\n\n" + content.rstrip() + "\n", encoding="utf-8")


# Persisted system Runtime profile for Conversation Burst / Turn Collector.
replace_once(
    "src/echo_masque/admin_runtime.py",
    "RUNTIME_DEFAULTS_VERSION = 4",
    "RUNTIME_DEFAULTS_VERSION = 5",
)
replace_once(
    "src/echo_masque/admin_runtime.py",
    '''class AdminRuntimeConfig(BaseModel):\n    model_config = ConfigDict(frozen=True)\n\n    adaptive: AdaptiveRuntimeProfile = Field(default_factory=AdaptiveRuntimeProfile)\n''',
    '''class ConversationBurstRuntimeProfile(BaseModel):\n    \"\"\"System-level live Turn Collector policy synchronized to Discord Connectors.\"\"\"\n\n    model_config = ConfigDict(frozen=True)\n\n    enabled: bool = True\n    quiet_window_ms: int = Field(default=3_000, ge=100, le=10_000)\n    max_wait_ms: int = Field(default=10_000, ge=500, le=30_000)\n    max_messages: int = Field(default=5, ge=1, le=20)\n    max_characters: int = Field(default=1_500, ge=100, le=10_000)\n\n    @model_validator(mode=\"after\")\n    def validate_wait_window(self) -> ConversationBurstRuntimeProfile:\n        if self.max_wait_ms < self.quiet_window_ms:\n            raise ValueError(\"max_wait_ms must be greater than or equal to quiet_window_ms\")\n        return self\n\n\nclass AdminRuntimeConfig(BaseModel):\n    model_config = ConfigDict(frozen=True)\n\n    adaptive: AdaptiveRuntimeProfile = Field(default_factory=AdaptiveRuntimeProfile)\n''',
)
replace_once(
    "src/echo_masque/admin_runtime.py",
    '''    utility_gateway: UtilityGatewayProfile = Field(default_factory=UtilityGatewayProfile)\n    default_judge_mode: JudgeModeValue = \"hybrid\"\n''',
    '''    utility_gateway: UtilityGatewayProfile = Field(default_factory=UtilityGatewayProfile)\n    conversation_burst: ConversationBurstRuntimeProfile = Field(\n        default_factory=ConversationBurstRuntimeProfile\n    )\n    default_judge_mode: JudgeModeValue = \"hybrid\"\n''',
)

# Admin Runtime snapshot API for Free Pool health/quota observations.
replace_once(
    "src/echo_masque/api/routes/admin.py",
    '''from echo_masque.services import RuntimeService\n''',
    '''from echo_masque.services import RuntimeService\nfrom echo_masque.utility_gateway_contracts import UtilityGatewaySnapshot\nfrom echo_masque.utility_gateway_router import UtilityGatewayRouter\n''',
)
replace_once(
    "src/echo_masque/api/routes/admin.py",
    '''@router.get(\n    \"/api/admin/runtime/utility-credentials\",\n    response_model=list[UtilityCredentialStatus],\n)\ndef list_utility_credentials(\n''',
    '''@router.get(\n    \"/api/admin/runtime/utility-gateway/snapshot\",\n    response_model=UtilityGatewaySnapshot,\n)\ndef utility_gateway_snapshot(\n    request: Request,\n    admin: AdminUserDependency,\n) -> UtilityGatewaySnapshot:\n    del admin\n    return UtilityGatewayRouter(runtime_service(request)).snapshot()\n\n\n@router.get(\n    \"/api/admin/runtime/utility-credentials\",\n    response_model=list[UtilityCredentialStatus],\n)\ndef list_utility_credentials(\n''',
)

# Connector-authenticated dynamic Runtime config endpoint.
replace_once(
    "src/echo_masque/api/routes/smart_participation.py",
    '''from echo_masque.authoring_generation import AuthoringRuntimeUnavailable\n''',
    '''from echo_masque.admin_runtime import ConversationBurstRuntimeProfile\nfrom echo_masque.authoring_generation import AuthoringRuntimeUnavailable\n''',
)
replace_once(
    "src/echo_masque/api/routes/smart_participation.py",
    '''from echo_masque.smart_participation_generation import SmartParticipationGenerationService\n''',
    '''from echo_masque.services import RuntimeService\nfrom echo_masque.smart_participation_generation import SmartParticipationGenerationService\n''',
)
replace_once(
    "src/echo_masque/api/routes/smart_participation.py",
    '''@router.get(\n    \"/connector-profiles\",\n    response_model=dict[str, SmartParticipationProfileView],\n)\ndef list_connector_profiles(\n''',
    '''@router.get(\n    \"/connector-runtime\",\n    response_model=ConversationBurstRuntimeProfile,\n)\ndef connector_runtime(\n    request: Request,\n    connection_id: str = Query(min_length=1, max_length=64),\n    authorization: Annotated[str | None, Header()] = None,\n) -> ConversationBurstRuntimeProfile:\n    \"\"\"Return the current system Turn Collector policy for one live Connector.\"\"\"\n\n    _authorize_connector(request, authorization)\n    del connection_id\n    runtime = cast(RuntimeService, request.app.state.runtime_service)\n    return runtime.config().conversation_burst\n\n\n@router.get(\n    \"/connector-profiles\",\n    response_model=dict[str, SmartParticipationProfileView],\n)\ndef list_connector_profiles(\n''',
)

# Fix expired cooling_down records being permanently excluded from Free Pool routing.
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''            if status == \"exhausted\" and reset_at is not None and reset_at <= now:\n                status = \"unknown\"\n            values.append(\n''',
    '''            if status == \"exhausted\" and reset_at is not None and reset_at <= now:\n                status = \"unknown\"\n            if status == \"cooling_down\" and (cooldown is None or cooldown <= now):\n                status = \"unknown\"\n            values.append(\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''            if status == \"exhausted\" and reset_at is not None and reset_at <= now:\n                status = \"unknown\"\n            if cooldown is not None and cooldown > now:\n                continue\n''',
    '''            if status == \"exhausted\" and reset_at is not None and reset_at <= now:\n                status = \"unknown\"\n            if status == \"cooling_down\" and (cooldown is None or cooldown <= now):\n                status = \"unknown\"\n            if cooldown is not None and cooldown > now:\n                continue\n''',
)

# New bootstrap defaults; Portal Runtime config will supersede these after sync.
replace_once(
    "connectors/discord/src/config.ts",
    '''      1_500,\n      100,\n      10_000\n''',
    '''      3_000,\n      100,\n      10_000\n''',
)
replace_once(
    "connectors/discord/src/config.ts",
    '''      4_000,\n      500,\n      30_000\n''',
    '''      10_000,\n      500,\n      30_000\n''',
)

# TurnIngress delegates live reconfiguration to TurnCollector.
replace_once(
    "connectors/discord/src/turnIngress.ts",
    '''  get enabled(): boolean {\n    return this.collector.enabled;\n  }\n\n  get pendingBurstScopeCount(): number {\n''',
    '''  get enabled(): boolean {\n    return this.collector.enabled;\n  }\n\n  get currentConfig(): TurnCollectorConfig {\n    return this.collector.currentConfig;\n  }\n\n  reconfigure(config: Partial<TurnCollectorConfig>): TurnCollectorConfig {\n    return this.collector.reconfigure(config);\n  }\n\n  get pendingBurstScopeCount(): number {\n''',
)

# RelayClient fetches dynamic global Smart Participation runtime config.
replace_once(
    "connectors/discord/src/relayClient.ts",
    '''export interface DiscordSmartParticipationScoreRequest {\n''',
    '''export interface DiscordConversationBurstRuntimeConfig {\n  enabled: boolean;\n  quiet_window_ms: number;\n  max_wait_ms: number;\n  max_messages: number;\n  max_characters: number;\n}\n\nexport interface DiscordSmartParticipationScoreRequest {\n''',
)
replace_once(
    "connectors/discord/src/relayClient.ts",
    '''  async syncServerCatalog(\n    payload: Omit<DiscordServerCatalogSync, \"connection_id\">\n  ): Promise<void> {\n''',
    '''  async getSmartParticipationRuntime(): Promise<DiscordConversationBurstRuntimeConfig> {\n    const query = new URLSearchParams({ connection_id: this.connectionId });\n    return this.request<DiscordConversationBurstRuntimeConfig>(\n      `/api/smart-participation/connector-runtime?${query.toString()}`\n    );\n  }\n\n  async syncServerCatalog(\n    payload: Omit<DiscordServerCatalogSync, \"connection_id\">\n  ): Promise<void> {\n''',
)

# Apply the latest persisted config during the existing deployment refresh loop.
replace_once(
    "connectors/discord/src/index.ts",
    '''async function refreshDeployments(): Promise<void> {\n  const next = await relay.listDeployments();\n  const botUserId = client.user?.id;\n''',
    '''async function refreshDeployments(): Promise<void> {\n  const [next, runtimeConfig] = await Promise.all([\n    relay.listDeployments(),\n    relay.getSmartParticipationRuntime().catch((error) => {\n      log(\"Unable to refresh dynamic Turn Collector config; keeping the last effective value.\", {\n        error: error instanceof Error ? error.message : String(error)\n      });\n      return null;\n    })\n  ]);\n  if (runtimeConfig) {\n    turnIngress.reconfigure({\n      enabled: runtimeConfig.enabled,\n      quietWindowMs: runtimeConfig.quiet_window_ms,\n      maxWaitMs: runtimeConfig.max_wait_ms,\n      maxMessages: runtimeConfig.max_messages,\n      maxCharacters: runtimeConfig.max_characters\n    });\n  }\n  const botUserId = client.user?.id;\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    webhookReady: next.filter(\n      (item) => item.identity_mode === \"webhook\" && item.webhook_status === \"active\"\n    ).length\n  });\n}\n''',
    '''    webhookReady: next.filter(\n      (item) => item.identity_mode === \"webhook\" && item.webhook_status === \"active\"\n    ).length,\n    turnCollector: turnIngress.currentConfig\n  });\n}\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      smart_participation_turn_collector_enabled: turnIngress.enabled,\n      smart_participation_turn_collector_pending_scopes:\n''',
    '''      smart_participation_turn_collector_enabled: turnIngress.enabled,\n      smart_participation_turn_collector_quiet_ms: turnIngress.currentConfig.quietWindowMs,\n      smart_participation_turn_collector_max_wait_ms: turnIngress.currentConfig.maxWaitMs,\n      smart_participation_turn_collector_max_messages: turnIngress.currentConfig.maxMessages,\n      smart_participation_turn_collector_max_characters:\n        turnIngress.currentConfig.maxCharacters,\n      smart_participation_turn_collector_pending_scopes:\n''',
)

# Focused TS regression: open bursts keep old snapshot; new bursts use new config.
append_once(
    "connectors/discord/src/turnCollector.test.ts",
    'it("keeps an open burst on its original config snapshot after reconfigure"',
    '''describe("TurnCollector live reconfiguration", () => {\n  afterEach(() => {\n    vi.useRealTimers();\n  });\n\n  it("keeps an open burst on its original config snapshot after reconfigure", async () => {\n    vi.useFakeTimers();\n    const bursts: ConversationBurst<SampleTurn>[] = [];\n    const collector = new TurnCollector<SampleTurn>(\n      { quietWindowMs: 3_000, maxWaitMs: 10_000, maxMessages: 5, maxCharacters: 1_500 },\n      (burst) => {\n        bursts.push(burst);\n      }\n    );\n\n    collector.add("channel", { id: "old", value: sample("old", "old"), characters: 3 });\n    collector.reconfigure({ quietWindowMs: 5_000, maxWaitMs: 15_000 });\n\n    expect(collector.currentConfig.quietWindowMs).toBe(5_000);\n    await vi.advanceTimersByTimeAsync(2_999);\n    expect(bursts).toHaveLength(0);\n    await vi.advanceTimersByTimeAsync(1);\n    expect(bursts.map((item) => item.itemIds)).toEqual([["old"]]);\n\n    collector.add("channel", { id: "new", value: sample("new", "new"), characters: 3 });\n    await vi.advanceTimersByTimeAsync(4_999);\n    expect(bursts).toHaveLength(1);\n    await vi.advanceTimersByTimeAsync(1);\n    expect(bursts.map((item) => item.itemIds)).toEqual([["old"], ["new"]]);\n  });\n});''',
)

# Focused backend regression tests.
Path("tests/test_observability_runtime_control.py").write_text(
    '''from datetime import UTC, datetime, timedelta\nfrom pathlib import Path\n\nfrom cryptography.fernet import Fernet\nfrom pydantic import SecretStr\n\nfrom echo_masque.admin_runtime import ConversationBurstRuntimeProfile, UtilityGatewayProfile, UtilityProviderMember\nfrom echo_masque.api import create_app\nfrom echo_masque.auth import SYSTEM_RUNTIME_USER_ID\nfrom echo_masque.config import Settings\nfrom echo_masque.credentials import CredentialVault\nfrom echo_masque.persistence.utility_gateway_models import UtilityProviderStateRecord\nfrom echo_masque.utility_gateway_router import UtilityGatewayRouter\n\n\ndef settings(path: Path) -> Settings:\n    return Settings(\n        environment=\"test\",\n        database_url=f\"sqlite:///{path}\",\n        legacy_local_user_enabled=False,\n        public_registration_enabled=False,\n        credential_encryption_keys=SecretStr(Fernet.generate_key().decode(\"ascii\")),\n    )\n\n\ndef test_conversation_burst_runtime_defaults_and_bounds() -> None:\n    profile = ConversationBurstRuntimeProfile()\n    assert profile.quiet_window_ms == 3_000\n    assert profile.max_wait_ms == 10_000\n    assert profile.max_messages == 5\n    assert profile.max_characters == 1_500\n\n\ndef test_expired_cooling_down_member_becomes_probe_eligible(tmp_path: Path) -> None:\n    app = create_app(settings(tmp_path / \"utility.db\"))\n    runtime = app.state.runtime_service\n    member = UtilityProviderMember(\n        id=\"free_provider\",\n        name=\"Free Provider\",\n        provider=\"groq\",\n        base_url=\"https://example.test\",\n        model=\"free-model\",\n        capabilities=(\"semantic_judge\",),\n        free_only=True,\n        priority=1,\n    )\n    runtime.save(\n        runtime.config().model_copy(\n            update={\n                \"utility_gateway\": UtilityGatewayProfile(\n                    enabled=True,\n                    routing_strategy=\"fixed_priority\",\n                    members=(member,),\n                )\n            }\n        )\n    )\n    runtime.credential_vault.set_scope(\n        owner_id=SYSTEM_RUNTIME_USER_ID,\n        scope_kind=CredentialVault.runtime_scope_kind,\n        scope_id=\"utility:free_provider\",\n        value=SecretStr(\"test-key\"),\n        actor_user_id=SYSTEM_RUNTIME_USER_ID,\n        resource_type=\"utility_gateway\",\n    )\n    with runtime.repository.database.session() as session:\n        session.add(\n            UtilityProviderStateRecord(\n                member_id=member.id,\n                provider=member.provider,\n                model=member.model,\n                status=\"cooling_down\",\n                cooldown_until=datetime.now(UTC) - timedelta(seconds=1),\n            )\n        )\n        session.commit()\n\n    router = UtilityGatewayRouter(runtime)\n    assert router.snapshot().members[0].status == \"unknown\"\n    assert [item.id for item in router._members(\"semantic_judge\")] == [member.id]\n''',
    encoding="utf-8",
)
