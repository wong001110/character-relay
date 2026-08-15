# ruff: noqa
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor: {path}: {old[:100]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"non-unique anchor: {path}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Backend connector heartbeat contract.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    last_gateway_message_id: str = Field(default="", max_length=200)\n    last_gateway_mentioned_bot: bool = False\n\n\nclass DiscordConnectorEventItem(BaseModel):\n''',
    '''    last_gateway_message_id: str = Field(default="", max_length=200)\n    last_gateway_mentioned_bot: bool = False\n    turn_collector_enabled: bool = False\n    turn_collector_quiet_window_ms: int = Field(default=0, ge=0, le=60_000)\n    turn_collector_max_wait_ms: int = Field(default=0, ge=0, le=120_000)\n    turn_collector_max_messages: int = Field(default=0, ge=0, le=100)\n    turn_collector_max_characters: int = Field(default=0, ge=0, le=100_000)\n    turn_collector_pending_burst_scope_count: int = Field(default=0, ge=0, le=100_000)\n    turn_collector_pending_preflight_scope_count: int = Field(default=0, ge=0, le=100_000)\n    turn_collector_candidate_messages: int = Field(default=0, ge=0)\n    turn_collector_bypass_messages: int = Field(default=0, ge=0)\n    turn_collector_bursts: int = Field(default=0, ge=0)\n    turn_collector_collected_messages: int = Field(default=0, ge=0)\n    turn_collector_collapsed_messages: int = Field(default=0, ge=0)\n    turn_collector_interaction_bypasses: int = Field(default=0, ge=0)\n    turn_collector_bypass_reasons: dict[str, int] = Field(default_factory=dict, max_length=40)\n    turn_collector_last_burst_at: str = Field(default="", max_length=64)\n    turn_collector_last_burst_id: str = Field(default="", max_length=80)\n    turn_collector_last_flush_reason: str = Field(default="", max_length=80)\n\n\nclass DiscordConnectorEventItem(BaseModel):\n''',
)

replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    '''        last_gateway_message_at: str = "",\n        last_gateway_message_id: str = "",\n        last_gateway_mentioned_bot: bool = False,\n    ) -> bool:\n''',
    '''        last_gateway_message_at: str = "",\n        last_gateway_message_id: str = "",\n        last_gateway_mentioned_bot: bool = False,\n        turn_collector_enabled: bool = False,\n        turn_collector_quiet_window_ms: int = 0,\n        turn_collector_max_wait_ms: int = 0,\n        turn_collector_max_messages: int = 0,\n        turn_collector_max_characters: int = 0,\n        turn_collector_pending_burst_scope_count: int = 0,\n        turn_collector_pending_preflight_scope_count: int = 0,\n        turn_collector_candidate_messages: int = 0,\n        turn_collector_bypass_messages: int = 0,\n        turn_collector_bursts: int = 0,\n        turn_collector_collected_messages: int = 0,\n        turn_collector_collapsed_messages: int = 0,\n        turn_collector_interaction_bypasses: int = 0,\n        turn_collector_bypass_reasons: dict[str, int] | None = None,\n        turn_collector_last_burst_at: str = "",\n        turn_collector_last_burst_id: str = "",\n        turn_collector_last_flush_reason: str = "",\n    ) -> bool:\n''',
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            metadata["last_gateway_message_id"] = last_gateway_message_id\n            metadata["last_gateway_mentioned_bot"] = last_gateway_mentioned_bot\n            record.external_account_id = external_account_id\n''',
    '''            metadata["last_gateway_message_id"] = last_gateway_message_id\n            metadata["last_gateway_mentioned_bot"] = last_gateway_mentioned_bot\n            metadata["turn_collector_enabled"] = turn_collector_enabled\n            metadata["turn_collector_quiet_window_ms"] = turn_collector_quiet_window_ms\n            metadata["turn_collector_max_wait_ms"] = turn_collector_max_wait_ms\n            metadata["turn_collector_max_messages"] = turn_collector_max_messages\n            metadata["turn_collector_max_characters"] = turn_collector_max_characters\n            metadata["turn_collector_pending_burst_scope_count"] = (\n                turn_collector_pending_burst_scope_count\n            )\n            metadata["turn_collector_pending_preflight_scope_count"] = (\n                turn_collector_pending_preflight_scope_count\n            )\n            metadata["turn_collector_candidate_messages"] = turn_collector_candidate_messages\n            metadata["turn_collector_bypass_messages"] = turn_collector_bypass_messages\n            metadata["turn_collector_bursts"] = turn_collector_bursts\n            metadata["turn_collector_collected_messages"] = turn_collector_collected_messages\n            metadata["turn_collector_collapsed_messages"] = turn_collector_collapsed_messages\n            metadata["turn_collector_interaction_bypasses"] = turn_collector_interaction_bypasses\n            metadata["turn_collector_bypass_reasons"] = turn_collector_bypass_reasons or {}\n            metadata["turn_collector_last_burst_at"] = turn_collector_last_burst_at\n            metadata["turn_collector_last_burst_id"] = turn_collector_last_burst_id\n            metadata["turn_collector_last_flush_reason"] = turn_collector_last_flush_reason\n            record.external_account_id = external_account_id\n''',
)

replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''        last_gateway_message_at=payload.last_gateway_message_at,\n        last_gateway_message_id=payload.last_gateway_message_id,\n        last_gateway_mentioned_bot=payload.last_gateway_mentioned_bot,\n    )\n''',
    '''        last_gateway_message_at=payload.last_gateway_message_at,\n        last_gateway_message_id=payload.last_gateway_message_id,\n        last_gateway_mentioned_bot=payload.last_gateway_mentioned_bot,\n        turn_collector_enabled=payload.turn_collector_enabled,\n        turn_collector_quiet_window_ms=payload.turn_collector_quiet_window_ms,\n        turn_collector_max_wait_ms=payload.turn_collector_max_wait_ms,\n        turn_collector_max_messages=payload.turn_collector_max_messages,\n        turn_collector_max_characters=payload.turn_collector_max_characters,\n        turn_collector_pending_burst_scope_count=payload.turn_collector_pending_burst_scope_count,\n        turn_collector_pending_preflight_scope_count=payload.turn_collector_pending_preflight_scope_count,\n        turn_collector_candidate_messages=payload.turn_collector_candidate_messages,\n        turn_collector_bypass_messages=payload.turn_collector_bypass_messages,\n        turn_collector_bursts=payload.turn_collector_bursts,\n        turn_collector_collected_messages=payload.turn_collector_collected_messages,\n        turn_collector_collapsed_messages=payload.turn_collector_collapsed_messages,\n        turn_collector_interaction_bypasses=payload.turn_collector_interaction_bypasses,\n        turn_collector_bypass_reasons=payload.turn_collector_bypass_reasons,\n        turn_collector_last_burst_at=payload.turn_collector_last_burst_at,\n        turn_collector_last_burst_id=payload.turn_collector_last_burst_id,\n        turn_collector_last_flush_reason=payload.turn_collector_last_flush_reason,\n    )\n''',
)

# Register admin observation route.
replace_once(
    "src/echo_masque/api/routes/__init__.py",
    "from echo_masque.api.routes.connectors import router as connectors_router\n",
    "from echo_masque.api.routes.connectors import router as connectors_router\nfrom echo_masque.api.routes.conversation_burst_observability import (\n    router as conversation_burst_observability_router,\n)\n",
)
replace_once(
    "src/echo_masque/api/routes/__init__.py",
    '    "connectors_router",\n    "conversation_intelligence_router",\n',
    '    "connectors_router",\n    "conversation_burst_observability_router",\n    "conversation_intelligence_router",\n',
)
replace_once(
    "src/echo_masque/api/app.py",
    "    connectors_router,\n    conversation_intelligence_router,\n",
    "    connectors_router,\n    conversation_burst_observability_router,\n    conversation_intelligence_router,\n",
)
replace_once(
    "src/echo_masque/api/app.py",
    "    app.include_router(admin_router)\n    app.include_router(provider_traces_router)\n",
    "    app.include_router(admin_router)\n    app.include_router(conversation_burst_observability_router)\n    app.include_router(provider_traces_router)\n",
)

# Connector heartbeat payload.
replace_once(
    "connectors/discord/src/types.ts",
    '''  last_gateway_message_id: string;\n  last_gateway_mentioned_bot: boolean;\n}\n\nexport interface DiscordWebhookRegistration {\n''',
    '''  last_gateway_message_id: string;\n  last_gateway_mentioned_bot: boolean;\n  turn_collector_enabled: boolean;\n  turn_collector_quiet_window_ms: number;\n  turn_collector_max_wait_ms: number;\n  turn_collector_max_messages: number;\n  turn_collector_max_characters: number;\n  turn_collector_pending_burst_scope_count: number;\n  turn_collector_pending_preflight_scope_count: number;\n  turn_collector_candidate_messages: number;\n  turn_collector_bypass_messages: number;\n  turn_collector_bursts: number;\n  turn_collector_collected_messages: number;\n  turn_collector_collapsed_messages: number;\n  turn_collector_interaction_bypasses: number;\n  turn_collector_bypass_reasons: Record<string, number>;\n  turn_collector_last_burst_at: string;\n  turn_collector_last_burst_id: string;\n  turn_collector_last_flush_reason: string;\n}\n\nexport interface DiscordWebhookRegistration {\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''  const user = client.user;\n  if (!user) return;\n  await relay.heartbeat({\n''',
    '''  const user = client.user;\n  if (!user) return;\n  const turnCollectorConfig = turnIngress.currentConfig;\n  await relay.heartbeat({\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    last_gateway_message_at: lastGatewayMessageAt ?? "",\n    last_gateway_message_id: lastGatewayMessageId ?? "",\n    last_gateway_mentioned_bot: lastGatewayMentionedBot\n  });\n''',
    '''    last_gateway_message_at: lastGatewayMessageAt ?? "",\n    last_gateway_message_id: lastGatewayMessageId ?? "",\n    last_gateway_mentioned_bot: lastGatewayMentionedBot,\n    turn_collector_enabled: turnCollectorConfig.enabled,\n    turn_collector_quiet_window_ms: turnCollectorConfig.quietWindowMs,\n    turn_collector_max_wait_ms: turnCollectorConfig.maxWaitMs,\n    turn_collector_max_messages: turnCollectorConfig.maxMessages,\n    turn_collector_max_characters: turnCollectorConfig.maxCharacters,\n    turn_collector_pending_burst_scope_count: turnIngress.pendingBurstScopeCount,\n    turn_collector_pending_preflight_scope_count: turnIngress.pendingPreflightScopeCount,\n    turn_collector_candidate_messages: turnCollectorCandidateMessageCount,\n    turn_collector_bypass_messages: turnCollectorBypassMessageCount,\n    turn_collector_bursts: turnCollectorBurstCount,\n    turn_collector_collected_messages: turnCollectorCollectedMessageCount,\n    turn_collector_collapsed_messages: turnCollectorCollapsedMessageCount,\n    turn_collector_interaction_bypasses: turnCollectorInteractionBypassCount,\n    turn_collector_bypass_reasons: { ...turnCollectorBypassReasons },\n    turn_collector_last_burst_at: turnCollectorLastBurstAt ?? "",\n    turn_collector_last_burst_id: turnCollectorLastBurstId ?? "",\n    turn_collector_last_flush_reason: turnCollectorLastFlushReason ?? ""\n  });\n''',
)

# Portal types and live panel.
replace_once(
    "web/src/ConversationBurstRuntimePanel.tsx",
    '''interface Props {\n  config: ConversationBurstRuntimeConfig;\n  zh: boolean;\n  onChange: (config: ConversationBurstRuntimeConfig) => void;\n}\n''',
    '''export interface ConversationBurstConnectorObservation {\n  connection_id: string;\n  display_name: string;\n  status: string;\n  last_seen_at: string | null;\n  effective_config: ConversationBurstRuntimeConfig;\n  pending_burst_scopes: number;\n  pending_preflight_scopes: number;\n  candidate_messages: number;\n  bypass_messages: number;\n  burst_count: number;\n  collected_messages: number;\n  collapsed_messages: number;\n  interaction_bypasses: number;\n  bypass_reasons: Record<string, number>;\n  last_burst_at: string | null;\n  last_burst_id: string;\n  last_flush_reason: string;\n}\n\nexport interface ConversationBurstObservation {\n  connectors: ConversationBurstConnectorObservation[];\n  bursts_24h: number;\n  collected_messages_24h: number;\n  collapsed_messages_24h: number;\n  last_persisted_burst: {\n    occurred_at: string;\n    connection_id: string;\n    guild_id: string;\n    channel_id: string;\n    burst_id: string;\n    flush_reason: string;\n    message_count: number;\n    author_count: number;\n    collapsed_message_count: number;\n    collection_latency_ms: number;\n  } | null;\n  observation_source: string;\n}\n\ninterface Props {\n  config: ConversationBurstRuntimeConfig;\n  observation: ConversationBurstObservation | null;\n  zh: boolean;\n  onChange: (config: ConversationBurstRuntimeConfig) => void;\n}\n''',
)
replace_once(
    "web/src/ConversationBurstRuntimePanel.tsx",
    '''export function ConversationBurstRuntimePanel({ config, zh, onChange }: Props) {\n''',
    '''export function ConversationBurstRuntimePanel({ config, observation, zh, onChange }: Props) {\n''',
)
replace_once(
    "web/src/ConversationBurstRuntimePanel.tsx",
    '''      <p className="section-help">{zh ? "保存后由 Connector 在运行中同步，无需重启。已经打开的 burst 保持创建时的参数；新 burst 使用最新配置。明确角色名、Reply 与 Interaction 仍走即时 fast path。" : "Changes sync into the live Connector without restart. Open bursts keep their original timing snapshot; new bursts use the latest config. Explicit addressing, replies, and interactions remain immediate."}</p>\n''',
    '''      <p className="section-help">{zh ? "保存后由 Connector 在运行中同步，无需重启。已经打开的 burst 保持创建时的参数；新 burst 使用最新配置。明确角色名、Reply 与 Interaction 仍走即时 fast path。" : "Changes sync into the live Connector without restart. Open bursts keep their original timing snapshot; new bursts use the latest config. Explicit addressing, replies, and interactions remain immediate."}</p>\n      <div className="conversation-burst-live-grid">\n        <div><span>{zh ? "当前 Pending Burst" : "Pending bursts"}</span><strong>{observation?.connectors.reduce((sum, item) => sum + item.pending_burst_scopes, 0) ?? 0}</strong></div>\n        <div><span>{zh ? "24h Bursts" : "Bursts / 24h"}</span><strong>{observation?.bursts_24h ?? 0}</strong></div>\n        <div><span>{zh ? "24h 收集消息" : "Collected / 24h"}</span><strong>{observation?.collected_messages_24h ?? 0}</strong></div>\n        <div><span>{zh ? "24h 合并消息" : "Collapsed / 24h"}</span><strong>{observation?.collapsed_messages_24h ?? 0}</strong></div>\n      </div>\n      {observation?.last_persisted_burst && (\n        <div className="conversation-burst-last">\n          <strong>{zh ? "最近一次 Burst" : "Last burst"}</strong>\n          <span>{new Date(observation.last_persisted_burst.occurred_at).toLocaleString()} · {observation.last_persisted_burst.message_count} {zh ? "条消息" : "messages"} · {observation.last_persisted_burst.collection_latency_ms} ms · {observation.last_persisted_burst.flush_reason}</span>\n        </div>\n      )}\n      {observation?.connectors.map((connector) => (\n        <div className="conversation-burst-connector" key={connector.connection_id}>\n          <div><strong>{connector.display_name}</strong><span>{connector.status}</span></div>\n          <small>{zh ? "Connector 实际参数" : "Effective Connector config"}: {seconds(connector.effective_config.quiet_window_ms)}s / {seconds(connector.effective_config.max_wait_ms)}s · pending {connector.pending_burst_scopes} · session bursts {connector.burst_count} · collapsed {connector.collapsed_messages}</small>\n        </div>\n      ))}\n''',
)

# System Intelligence polling.
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''  ConversationBurstRuntimePanel,\n  type ConversationBurstRuntimeConfig\n''',
    '''  ConversationBurstRuntimePanel,\n  type ConversationBurstObservation,\n  type ConversationBurstRuntimeConfig\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''async function loadUtilitySnapshot(): Promise<UtilityGatewayRuntimeSnapshot | null> {\n  const response = await fetch("/api/admin/runtime/utility-gateway/snapshot", { credentials: "include" });\n  if (!response.ok) return null;\n  return response.json() as Promise<UtilityGatewayRuntimeSnapshot>;\n}\n''',
    '''async function loadUtilitySnapshot(): Promise<UtilityGatewayRuntimeSnapshot | null> {\n  const response = await fetch("/api/admin/runtime/utility-gateway/snapshot", { credentials: "include" });\n  if (!response.ok) return null;\n  return response.json() as Promise<UtilityGatewayRuntimeSnapshot>;\n}\n\nasync function loadBurstObservation(): Promise<ConversationBurstObservation | null> {\n  const response = await fetch("/api/admin/runtime/conversation-burst/snapshot", { credentials: "include" });\n  if (!response.ok) return null;\n  return response.json() as Promise<ConversationBurstObservation>;\n}\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''  const [runtimeSnapshot, setRuntimeSnapshot] = useState<UtilityGatewayRuntimeSnapshot | null>(null);\n''',
    '''  const [runtimeSnapshot, setRuntimeSnapshot] = useState<UtilityGatewayRuntimeSnapshot | null>(null);\n  const [burstObservation, setBurstObservation] = useState<ConversationBurstObservation | null>(null);\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''    const [credentials, snapshot] = await Promise.all([loadUtilityCredentials(), loadUtilitySnapshot()]);\n    setCredentialStatus(credentials);\n    setRuntimeSnapshot(snapshot);\n''',
    '''    const [credentials, snapshot, bursts] = await Promise.all([\n      loadUtilityCredentials(),\n      loadUtilitySnapshot(),\n      loadBurstObservation()\n    ]);\n    setCredentialStatus(credentials);\n    setRuntimeSnapshot(snapshot);\n    setBurstObservation(bursts);\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''    void Promise.all([api.getAdminRuntime(), loadUtilityCredentials(), loadUtilitySnapshot()])\n      .then(([value, credentials, snapshot]) => {\n''',
    '''    void Promise.all([\n      api.getAdminRuntime(),\n      loadUtilityCredentials(),\n      loadUtilitySnapshot(),\n      loadBurstObservation()\n    ])\n      .then(([value, credentials, snapshot, bursts]) => {\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''          setCredentialStatus(credentials);\n          setRuntimeSnapshot(snapshot);\n''',
    '''          setCredentialStatus(credentials);\n          setRuntimeSnapshot(snapshot);\n          setBurstObservation(bursts);\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''    const timer = window.setInterval(() => { void loadUtilitySnapshot().then(setRuntimeSnapshot); }, 15_000);\n''',
    '''    const timer = window.setInterval(() => {\n      void loadUtilitySnapshot().then(setRuntimeSnapshot);\n      void loadBurstObservation().then(setBurstObservation);\n    }, 15_000);\n''',
)
replace_once(
    "web/src/SemanticRoutingJudgeDock.tsx",
    '''          <ConversationBurstRuntimePanel config={view.config.conversation_burst} zh={zh} onChange={updateConversationBurst} />\n''',
    '''          <ConversationBurstRuntimePanel config={view.config.conversation_burst} observation={burstObservation} zh={zh} onChange={updateConversationBurst} />\n''',
)

# Event log visibility.
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  "runtime_silent",\n  "context_built",\n''',
    '''  "runtime_silent",\n  "smart_participation_burst_flushed",\n  "context_built",\n''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },\n  context_built: { en: "Context built", zh: "角色 Context 已构建" },\n''',
    '''  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },\n  smart_participation_burst_flushed: { en: "Conversation Burst flushed", zh: "Conversation Burst 已 Flush" },\n  context_built: { en: "Context built", zh: "角色 Context 已构建" },\n''',
)

styles = Path("web/src/styles.css")
css = styles.read_text(encoding="utf-8")
marker = "/* Conversation Burst Live Observation */"
if marker not in css:
    css += r'''\n\n/* Conversation Burst Live Observation */\n.conversation-burst-live-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }\n.conversation-burst-live-grid > div { display: grid; gap: 3px; padding: 10px; border: 1px solid var(--line); border-radius: 12px; background: var(--soft-panel); }\n.conversation-burst-live-grid span { color: var(--muted-text); font-size: .72rem; }\n.conversation-burst-live-grid strong { font-size: 1.15rem; }\n.conversation-burst-last, .conversation-burst-connector { display: grid; gap: 4px; padding: 10px 12px; border: 1px dashed var(--line); border-radius: 12px; margin-bottom: 8px; }\n.conversation-burst-last span, .conversation-burst-connector small { color: var(--muted-text); }\n.conversation-burst-connector > div { display: flex; justify-content: space-between; gap: 10px; }\n.conversation-burst-connector > div span { color: var(--muted-text); text-transform: uppercase; font-size: .72rem; }\n@media (max-width: 720px) { .conversation-burst-live-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }\n'''
    styles.write_text(css, encoding="utf-8")
