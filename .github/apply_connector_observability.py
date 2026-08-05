from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {relative}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(relative: str, marker: str, content: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


def write_file(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


# Persistence exports.
replace_once(
    "src/echo_masque/persistence/__init__.py",
    "from echo_masque.persistence.database import Database\nfrom echo_masque.persistence.deployment_models import (",
    "from echo_masque.persistence.database import Database\n"
    "from echo_masque.persistence.deployment_log_models import DeploymentLogRecord\n"
    "from echo_masque.persistence.deployment_log_repository import DeploymentLogRepository\n"
    "from echo_masque.persistence.deployment_models import (",
)
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '    "DeploymentMessageIdentityRecord",\n    "DeploymentRepository",',
    '    "DeploymentLogRecord",\n    "DeploymentLogRepository",\n'
    '    "DeploymentMessageIdentityRecord",\n    "DeploymentRepository",',
)

# Public deployment log schema.
replace_once(
    "src/echo_masque/api/deployment_schemas.py",
    "from pydantic import BaseModel, Field\n\nfrom echo_masque.persistence.deployment_models import (",
    "from pydantic import BaseModel, Field\n\n"
    "from echo_masque.persistence.deployment_log_models import DeploymentLogRecord\n"
    "from echo_masque.persistence.deployment_models import (",
)
append_once(
    "src/echo_masque/api/deployment_schemas.py",
    "class DeploymentLogView(BaseModel):",
    '''
class DeploymentLogView(BaseModel):
    id: str
    connection_id: str
    deployment_id: str
    platform: PlatformId
    level: Literal["debug", "info", "warning", "error"]
    event_type: str
    message: str
    workspace_id: str
    channel_id: str
    thread_id: str
    source_message_id: str
    details: dict[str, object]
    created_at: datetime

    @classmethod
    def from_record(cls, record: DeploymentLogRecord) -> "DeploymentLogView":
        try:
            raw = json.loads(record.details_json)
        except json.JSONDecodeError:
            raw = {}
        details = raw if isinstance(raw, dict) else {}
        return cls(
            id=record.id,
            connection_id=record.connection_id,
            deployment_id=record.deployment_id,
            platform=cast(PlatformId, record.platform),
            level=cast(Literal["debug", "info", "warning", "error"], record.level),
            event_type=record.event_type,
            message=record.message,
            workspace_id=record.workspace_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            source_message_id=record.source_message_id,
            details=cast(dict[str, object], details),
            created_at=record.created_at,
        )
''',
)

# Owner-facing deployment log API.
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "    CharacterDeploymentUpdate,\n    CharacterDeploymentView,\n    DiscordServerCatalogView,",
    "    CharacterDeploymentUpdate,\n    CharacterDeploymentView,\n"
    "    DeploymentLogView,\n    DiscordServerCatalogView,",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "    DeploymentConflict,\n    DeploymentRepository,\n    InteractionRepository,",
    "    DeploymentConflict,\n    DeploymentLogRepository,\n"
    "    DeploymentRepository,\n    InteractionRepository,",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "def deployment_repository(request: Request) -> DeploymentRepository:\n"
    "    return cast(DeploymentRepository, request.app.state.deployment_repository)\n\n\n"
    "def character_repository(request: Request) -> Repository:",
    "def deployment_repository(request: Request) -> DeploymentRepository:\n"
    "    return cast(DeploymentRepository, request.app.state.deployment_repository)\n\n\n"
    "def deployment_log_repository(request: Request) -> DeploymentLogRepository:\n"
    "    return cast(DeploymentLogRepository, request.app.state.deployment_log_repository)\n\n\n"
    "def character_repository(request: Request) -> Repository:",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "    interaction_repository(request).delete_connection_scope(\n"
    "        owner_id=user.id,\n"
    "        connection_id=connection_id,\n"
    "        server_profile_ids=profile_ids,\n"
    "    )",
    "    deployment_log_repository(request).delete_connection_scope(connection_id)\n"
    "    interaction_repository(request).delete_connection_scope(\n"
    "        owner_id=user.id,\n"
    "        connection_id=connection_id,\n"
    "        server_profile_ids=profile_ids,\n"
    "    )",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '@router.get("/deployments", response_model=list[CharacterDeploymentView])',
    '''@router.get("/deployment-logs", response_model=list[DeploymentLogView])
def list_deployment_logs(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    deployment_id: str | None = Query(default=None, max_length=64),
    level: str | None = Query(
        default=None,
        pattern="^(debug|info|warning|error)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DeploymentLogView]:
    if connection_id is not None:
        connection = deployment_repository(request).get_connection(connection_id, user.id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Platform connection not found.")
    records = deployment_log_repository(request).list_events(
        user.id,
        connection_id=connection_id,
        deployment_id=deployment_id,
        level=level,
        limit=limit,
    )
    return [DeploymentLogView.from_record(item) for item in records]


@router.get("/deployments", response_model=list[CharacterDeploymentView])''',
)

# Connector-facing events are captured at the API boundary, without message text.
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    DeploymentRepository,\n    DiscordIdentityRepository,",
    "    DeploymentLogRepository,\n    DeploymentRepository,\n    DiscordIdentityRepository,",
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "def deployment_repository(request: Request) -> DeploymentRepository:\n"
    "    return cast(DeploymentRepository, request.app.state.deployment_repository)\n\n\n"
    "def identity_repository(request: Request) -> DiscordIdentityRepository:",
    "def deployment_repository(request: Request) -> DeploymentRepository:\n"
    "    return cast(DeploymentRepository, request.app.state.deployment_repository)\n\n\n"
    "def deployment_log_repository(request: Request) -> DeploymentLogRepository:\n"
    "    return cast(DeploymentLogRepository, request.app.state.deployment_log_repository)\n\n\n"
    "def identity_repository(request: Request) -> DiscordIdentityRepository:",
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    return views\n\n\n@router.put(\"/server-catalog\"",
    '''    deployment_log_repository(request).record(
        connection_id=connection_id,
        platform="discord",
        level="info",
        event_type="deployment_sync",
        message=f"Connector loaded {len(views)} active Discord deployment(s).",
        details={
            "deployment_ids": [item.deployment_id for item in views],
            "server_wide_count": sum(
                item.channel_scope_mode == "all_except" for item in views
            ),
            "pending_webhook_count": sum(
                item.identity_mode == "webhook" and item.webhook_status == "pending"
                for item in views
            ),
        },
        dedupe_seconds=120,
    )
    return views


@router.put("/server-catalog"''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    except KeyError as exc:\n"
    "        raise HTTPException(status_code=404, detail=\"Discord connection not found.\") from exc\n\n\n"
    "@router.put(\"/webhooks\"",
    '''    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    deployment_log_repository(request).record(
        connection_id=payload.connection_id,
        platform="discord",
        level="info",
        event_type="server_catalog_sync",
        message=f"Connector synchronized {len(payload.servers)} Discord server(s).",
        details={
            "servers": [
                {
                    "guild_id": item.guild_id,
                    "guild_name": item.guild_name,
                    "channel_count": len(item.channels),
                    "sticker_count": len(item.stickers),
                }
                for item in payload.servers
            ]
        },
        dedupe_seconds=120,
    )


@router.put("/webhooks"''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    identities.set_identity_status(\n"
    "        deployment_id=payload.deployment_id,\n"
    "        status=\"active\",\n"
    "    )\n"
    "    return DiscordWebhookRegistrationView(",
    "    identities.set_identity_status(\n"
    "        deployment_id=payload.deployment_id,\n"
    "        status=\"active\",\n"
    "    )\n"
    "    deployment_log_repository(request).record(\n"
    "        connection_id=payload.connection_id,\n"
    "        platform=\"discord\",\n"
    "        level=\"info\",\n"
    "        event_type=\"webhook_ready\",\n"
    "        message=\"Discord Webhook identity is ready for this Channel.\",\n"
    "        deployment_id=payload.deployment_id,\n"
    "        workspace_id=payload.workspace_id,\n"
    "        channel_id=payload.channel_id,\n"
    "        thread_id=payload.thread_id,\n"
    "        details={\"webhook_id\": payload.webhook_id},\n"
    "    )\n"
    "    return DiscordWebhookRegistrationView(",
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    if not updated:\n"
    "        raise HTTPException(status_code=404, detail=\"Discord connection not found.\")\n\n\n"
    "@router.post(\"/stickers/resolve\"",
    '''    if not updated:
        raise HTTPException(status_code=404, detail="Discord connection not found.")
    deployment_log_repository(request).record(
        connection_id=payload.connection_id,
        platform="discord",
        level="error" if payload.status == "error" else "info",
        event_type="connector_heartbeat",
        message=f"Discord Connector reported {payload.status}.",
        details={
            "bot_user_id": payload.bot_user_id,
            "bot_display_name": payload.bot_display_name,
            "last_error": payload.last_error,
        },
        dedupe_seconds=120,
    )


@router.post("/stickers/resolve"''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''@router.post("/messages", response_model=DiscordConnectorReplyView)
async def process_discord_message(
    payload: DiscordInboundMessage,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordConnectorReplyView:
    _authorize_connector(request, authorization)
    try:
        return await connector_runtime(request).respond(payload)
    except ConnectorRuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Character provider failed: {exc}",
        ) from exc
''',
    '''@router.post("/messages", response_model=DiscordConnectorReplyView)
async def process_discord_message(
    payload: DiscordInboundMessage,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordConnectorReplyView:
    _authorize_connector(request, authorization)
    logs = deployment_log_repository(request)
    logs.record(
        connection_id=payload.connection_id,
        platform="discord",
        level="info",
        event_type="runtime_message_received",
        message="Discord message reached the Character Runtime.",
        deployment_id=payload.deployment_id,
        workspace_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        source_message_id=payload.message_id,
        details={
            "guild_name": payload.guild_name,
            "channel_name": payload.channel_name,
            "thread_name": payload.thread_name,
            "mentioned_bot": payload.mentioned_bot,
            "replied_to_bot": payload.replied_to_bot,
            "smart_candidate": payload.smart_candidate,
            "author_is_bot": payload.author_is_bot,
            "sticker_count": len(payload.stickers),
            "recent_context_count": len(payload.recent_messages),
            "has_readable_text": bool(payload.text.strip()),
        },
    )
    try:
        reply = await connector_runtime(request).respond(payload)
        logs.record(
            connection_id=payload.connection_id,
            platform="discord",
            level="info",
            event_type="runtime_reply" if reply.action == "reply" else "runtime_silent",
            message=(
                "Character Runtime generated a reply."
                if reply.action == "reply"
                else "Character Runtime intentionally stayed silent."
            ),
            deployment_id=payload.deployment_id,
            workspace_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            source_message_id=payload.message_id,
            details={
                "action": reply.action,
                "reason": reply.reason,
                "latency_ms": reply.latency_ms,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "has_reply_text": bool(reply.text),
            },
        )
        return reply
    except ConnectorRuntimeError as exc:
        logs.record(
            connection_id=payload.connection_id,
            platform="discord",
            level="warning",
            event_type="runtime_rejected",
            message=str(exc),
            deployment_id=payload.deployment_id,
            workspace_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            source_message_id=payload.message_id,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logs.record(
            connection_id=payload.connection_id,
            platform="discord",
            level="error",
            event_type="runtime_error",
            message=f"Character provider failed: {exc}",
            deployment_id=payload.deployment_id,
            workspace_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            source_message_id=payload.message_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Character provider failed: {exc}",
        ) from exc
''',
)

# Application wiring and account lifecycle.
replace_once(
    "src/echo_masque/api/__init__.py",
    "    Database,\n    DeploymentRepository,\n    DiscordIdentityRepository,",
    "    Database,\n    DeploymentLogRepository,\n"
    "    DeploymentRepository,\n    DiscordIdentityRepository,",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    deployment_repository = DeploymentRepository(database)\n"
    "    discord_identity_repository = DiscordIdentityRepository(database)",
    "    deployment_repository = DeploymentRepository(database)\n"
    "    deployment_log_repository = DeploymentLogRepository(database)\n"
    "    discord_identity_repository = DiscordIdentityRepository(database)",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "        deployment_repository,\n        discord_identity_repository,",
    "        deployment_repository,\n        deployment_log_repository,\n"
    "        discord_identity_repository,",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    app.state.deployment_repository = deployment_repository\n"
    "    app.state.discord_identity_repository = discord_identity_repository",
    "    app.state.deployment_repository = deployment_repository\n"
    "    app.state.deployment_log_repository = deployment_log_repository\n"
    "    app.state.discord_identity_repository = discord_identity_repository",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "    Database,\n    DeploymentRepository,\n    DiscordIdentityRepository,",
    "    Database,\n    DeploymentLogRepository,\n"
    "    DeploymentRepository,\n    DiscordIdentityRepository,",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "        deployment_repository: DeploymentRepository | None = None,\n"
    "        discord_identity_repository: DiscordIdentityRepository | None = None,",
    "        deployment_repository: DeploymentRepository | None = None,\n"
    "        deployment_log_repository: DeploymentLogRepository | None = None,\n"
    "        discord_identity_repository: DiscordIdentityRepository | None = None,",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "        self.deployment_repository = deployment_repository or DeploymentRepository(database)\n"
    "        self.discord_identity_repository = discord_identity_repository or DiscordIdentityRepository(\n",
    "        self.deployment_repository = deployment_repository or DeploymentRepository(database)\n"
    "        self.deployment_log_repository = (\n"
    "            deployment_log_repository or DeploymentLogRepository(database)\n"
    "        )\n"
    "        self.discord_identity_repository = discord_identity_repository or DiscordIdentityRepository(\n",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "        deployment_counts = self.deployment_repository.delete_owner(user_id)\n"
    "        deleted = super().delete_account(user_id, email=email)\n"
    "        return {\n"
    "            **deleted,\n"
    "            **evaluation_counts,",
    "        deployment_log_counts = self.deployment_log_repository.delete_owner(user_id)\n"
    "        deployment_counts = self.deployment_repository.delete_owner(user_id)\n"
    "        deleted = super().delete_account(user_id, email=email)\n"
    "        return {\n"
    "            **deleted,\n"
    "            **evaluation_counts,\n"
    "            **deployment_log_counts,",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "        deployment_counts = self.deployment_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        identity_counts = self.discord_identity_repository.claim_owner(",
    "        deployment_log_counts = self.deployment_log_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        deployment_counts = self.deployment_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n"
    "        identity_counts = self.discord_identity_repository.claim_owner(",
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    "            **evaluation_counts,\n            **deployment_counts,",
    "            **evaluation_counts,\n            **deployment_log_counts,\n"
    "            **deployment_counts,",
)

# Portal API types and client.
replace_once(
    "web/src/deploymentApi.ts",
    "async function errorMessage(response: Response): Promise<string> {",
    '''export type DeploymentLogLevel = "debug" | "info" | "warning" | "error";

export interface DeploymentLog {
  id: string;
  connection_id: string;
  deployment_id: string;
  platform: PlatformId;
  level: DeploymentLogLevel;
  event_type: string;
  message: string;
  workspace_id: string;
  channel_id: string;
  thread_id: string;
  source_message_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

async function errorMessage(response: Response): Promise<string> {''',
)
replace_once(
    "web/src/deploymentApi.ts",
    "  createDeployment: (payload: CharacterDeploymentCreate) =>",
    '''  listDeploymentLogs: (options: {
    connectionId?: string;
    deploymentId?: string;
    level?: DeploymentLogLevel | "all";
    limit?: number;
  } = {}) => {
    const query = new URLSearchParams({ limit: String(options.limit ?? 100) });
    if (options.connectionId) query.set("connection_id", options.connectionId);
    if (options.deploymentId) query.set("deployment_id", options.deploymentId);
    if (options.level && options.level !== "all") query.set("level", options.level);
    return request<DeploymentLog[]>(`/api/deployment-logs?${query.toString()}`);
  },
  createDeployment: (payload: CharacterDeploymentCreate) =>''',
)

# Portal integration and clearer lazy Webhook status.
replace_once(
    "web/src/DeploymentCenter.tsx",
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\n',
    'import { DeploymentLogsPanel } from "./DeploymentLogsPanel";\n'
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\n',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    "function destination(deployment: CharacterDeployment, zh: boolean): string {",
    '''function identityStatusLabel(
  deployment: CharacterDeployment,
  identity: DeploymentMessageIdentity,
  zh: boolean
): string {
  if (
    deployment.channel_scope_mode === "all_except" &&
    identity.mode === "webhook" &&
    identity.webhook_status === "pending"
  ) {
    return zh ? "首次回复时建立" : "created on first reply";
  }
  return statusLabel(identity.webhook_status);
}

function destination(deployment: CharacterDeployment, zh: boolean): string {''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    "  const [error, setError] = useState<string | null>(null);\n",
    "  const [error, setError] = useState<string | null>(null);\n"
    "  const [logDeployment, setLogDeployment] = useState<CharacterDeployment | null>(null);\n",
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    "                            {identity.display_name} · {statusLabel(identity.webhook_status)}",
    "                            {identity.display_name} · {identityStatusLabel(item, identity, zh)}",
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                      <div className="deployment-actions">
                        {!demoMode && (
                          <>''',
    '''                      <div className="deployment-actions">
                        <button
                          className="paper-button"
                          onClick={() => setLogDeployment(item)}
                        >
                          {zh ? "日志" : "Logs"}
                        </button>
                        {!demoMode && (
                          <>''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''      {selectedWorkspaceProfile && (
        <InteractionSessionsPanel
          demoMode={demoMode}
          zh={zh}
          serverProfile={selectedWorkspaceProfile}
          serverCatalog={selectedWorkspaceCatalog}
        />
      )}
    </main>''',
    '''      {selectedWorkspaceProfile && (
        <InteractionSessionsPanel
          demoMode={demoMode}
          zh={zh}
          serverProfile={selectedWorkspaceProfile}
          serverCatalog={selectedWorkspaceCatalog}
        />
      )}
      {logDeployment && (
        <DeploymentLogsPanel
          deployment={logDeployment}
          zh={zh}
          onClose={() => setLogDeployment(null)}
        />
      )}
    </main>''',
)
replace_once(
    "web/src/main.tsx",
    'import "./discordServerProfiles.css";\n',
    'import "./discordServerProfiles.css";\nimport "./deploymentLogs.css";\n',
)

# Pin the Discord Connector to Railway Singapore.
replace_once(
    "connectors/discord/railway.toml",
    "numReplicas = 1",
    'multiRegionConfig = { "asia-southeast1-eqsg3a" = { numReplicas = 1 } }',
)

# Focused API regression coverage.
write_file(
    "tests/test_deployment_logs.py",
    r'''
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.config import Settings

ADMIN_EMAIL = "logs-admin@example.com"
ADMIN_PASSWORD = "ConnectorLogsAdmin2026!"
CONNECTOR_SECRET = "connector-log-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Logs Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def test_connector_events_are_visible_without_message_content(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "deployment-logs.db"))
    client = TestClient(app)
    login(client)

    character = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Connector logs fixture",
            "subject_type": "companion",
            "persona_summary": "A concise Discord character.",
            "traits": ["calm"],
            "tags": ["discord"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use supplied context only.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    ).json()
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Discord Connector",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "connected",
            "metadata": {},
        },
    ).json()
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character["id"],
            "connection_id": connection["id"],
            "workspace_id": "guild-logs",
            "workspace_name": "Logs Guild",
            "channel_id": "channel-logs",
            "channel_name": "logs-room",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    ).json()
    identity = client.put(
        f"/api/deployment-identities/{deployment['id']}",
        json={
            "mode": "webhook",
            "display_name": "Ann",
            "avatar_url": None,
            "address_aliases": ["Ann"],
        },
    )
    assert identity.status_code == 200, identity.text
    assert identity.json()["webhook_status"] == "pending"
    assert deployment["status"] == "active"

    headers = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}
    synced = client.get(
        "/api/connectors/discord/deployments",
        params={"connection_id": connection["id"]},
        headers=headers,
    )
    assert synced.status_code == 200, synced.text

    async def respond(_payload: object) -> DiscordConnectorReplyView:
        return DiscordConnectorReplyView(
            action="reply",
            reason="model_reply",
            deployment_id=deployment["id"],
            character_display_name="Ann",
            text="A safe generated reply.",
            reply_to_message_id="message-logs",
            latency_ms=42,
            input_tokens=12,
            output_tokens=8,
        )

    app.state.discord_connector_runtime.respond = respond
    private_text = "PRIVATE MESSAGE CONTENT MUST NOT BE STORED"
    processed = client.post(
        "/api/connectors/discord/messages",
        headers=headers,
        json={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "message_id": "message-logs",
            "guild_id": "guild-logs",
            "guild_name": "Logs Guild",
            "channel_id": "channel-logs",
            "channel_name": "logs-room",
            "category_id": "",
            "thread_id": "",
            "thread_name": "",
            "author_id": "user-logs",
            "author_display_name": "Tester",
            "text": private_text,
            "mentioned_bot": True,
            "replied_to_bot": False,
            "smart_candidate": False,
            "author_is_bot": False,
            "stickers": [],
            "available_characters": [],
            "recent_messages": [],
            "interaction_session_id": "",
            "interaction_type": "",
            "interaction_intensity": "",
            "interaction_round": 0,
            "interaction_total_rounds": 0,
            "interaction_position": 0,
            "interaction_participant_count": 0,
            "interaction_target_user_id": "",
            "interaction_target_display_name": "",
        },
    )
    assert processed.status_code == 200, processed.text

    response = client.get(
        "/api/deployment-logs",
        params={
            "connection_id": connection["id"],
            "deployment_id": deployment["id"],
            "limit": 100,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    event_types = {item["event_type"] for item in payload}
    assert "deployment_sync" in event_types
    assert "runtime_message_received" in event_types
    assert "runtime_reply" in event_types
    assert private_text not in response.text
''',
)

# The workflow and patch script are temporary implementation scaffolding.
(ROOT / ".github/apply_connector_observability.py").unlink(missing_ok=True)
(ROOT / ".github/workflows/apply-connector-observability.yml").unlink(missing_ok=True)
