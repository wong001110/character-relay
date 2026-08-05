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


def replace_last(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    index = text.rfind(old)
    if index < 0:
        raise RuntimeError(f"Patch anchor not found in {relative}: {old[:120]!r}")
    path.write_text(text[:index] + new + text[index + len(old) :], encoding="utf-8")


def append_once(relative: str, marker: str, content: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


# Persistent Discord event records.
append_once(
    "src/echo_masque/persistence/deployment_models.py",
    "class DiscordConnectorEventRecord(Base):",
    '''
class DiscordConnectorEventRecord(Base):
    """Privacy-safe event emitted by the Discord Gateway connector."""

    __tablename__ = "discord_connector_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    thread_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    source_message_id: Mapped[str] = mapped_column(
        String(200), index=True, default="", nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    character_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
''',
)

replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "import json\nimport math\nfrom uuid import uuid4",
    "import json\nimport math\nfrom datetime import datetime\nfrom uuid import uuid4",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "    DiscordDeploymentScopeRecord,\n    DiscordServerCatalogRecord,",
    "    DiscordConnectorEventRecord,\n    DiscordDeploymentScopeRecord,\n"
    "    DiscordServerCatalogRecord,",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "class DeploymentConflict(RuntimeError):\n    \"\"\"Raised when a deployment or reusable server profile conflicts.\"\"\"\n",
    "class DeploymentConflict(RuntimeError):\n    \"\"\"Raised when a deployment or reusable server profile conflicts.\"\"\"\n\n\n"
    "_MAX_DISCORD_EVENTS_PER_CONNECTION = 5_000\n",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "            session.execute(\n                delete(DiscordServerCatalogRecord).where(\n"
    "                    DiscordServerCatalogRecord.owner_id == owner_id,\n"
    "                    DiscordServerCatalogRecord.connection_id == connection_id,\n"
    "                )\n            )\n            session.delete(record)",
    "            session.execute(\n                delete(DiscordServerCatalogRecord).where(\n"
    "                    DiscordServerCatalogRecord.owner_id == owner_id,\n"
    "                    DiscordServerCatalogRecord.connection_id == connection_id,\n"
    "                )\n            )\n"
    "            session.execute(\n                delete(DiscordConnectorEventRecord).where(\n"
    "                    DiscordConnectorEventRecord.owner_id == owner_id,\n"
    "                    DiscordConnectorEventRecord.connection_id == connection_id,\n"
    "                )\n            )\n            session.delete(record)",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "    def sync_discord_server_catalog(\n",
    '''    def record_discord_events(
        self,
        *,
        connection_id: str,
        events: list[dict[str, object]],
    ) -> int:
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.platform != "discord":
                raise KeyError("connection")

            requested_deployment_ids = {
                str(item.get("deployment_id", "")).strip()
                for item in events
                if str(item.get("deployment_id", "")).strip()
            }
            valid_deployment_ids = set(
                session.scalars(
                    select(CharacterDeploymentRecord.id).where(
                        CharacterDeploymentRecord.connection_id == connection_id,
                        CharacterDeploymentRecord.id.in_(requested_deployment_ids),
                    )
                )
            )
            invalid = requested_deployment_ids - valid_deployment_ids
            if invalid:
                raise ValueError("One or more Discord event deployment IDs are invalid.")

            inserted = 0
            for item in events:
                event_id = str(item["id"])
                if session.get(DiscordConnectorEventRecord, event_id) is not None:
                    continue
                occurred_at = item["occurred_at"]
                if not isinstance(occurred_at, datetime):
                    raise ValueError("Discord event occurred_at must be a datetime.")
                details = item.get("details", {})
                safe_details = details if isinstance(details, dict) else {}
                session.add(
                    DiscordConnectorEventRecord(
                        id=event_id,
                        owner_id=connection.owner_id,
                        connection_id=connection_id,
                        level=str(item["level"])[:16],
                        event_type=str(item["event_type"])[:80],
                        message=str(item["message"])[:300],
                        guild_id=str(item.get("guild_id", ""))[:200],
                        guild_name=str(item.get("guild_name", ""))[:160],
                        channel_id=str(item.get("channel_id", ""))[:200],
                        channel_name=str(item.get("channel_name", ""))[:160],
                        thread_id=str(item.get("thread_id", ""))[:200],
                        thread_name=str(item.get("thread_name", ""))[:160],
                        source_message_id=str(item.get("source_message_id", ""))[:200],
                        deployment_id=str(item.get("deployment_id", ""))[:64],
                        character_name=str(item.get("character_name", ""))[:160],
                        details_json=json.dumps(redact(safe_details), ensure_ascii=False),
                        occurred_at=occurred_at,
                    )
                )
                inserted += 1

            session.flush()
            overflow_ids = list(
                session.scalars(
                    select(DiscordConnectorEventRecord.id)
                    .where(DiscordConnectorEventRecord.connection_id == connection_id)
                    .order_by(
                        DiscordConnectorEventRecord.occurred_at.desc(),
                        DiscordConnectorEventRecord.id.desc(),
                    )
                    .offset(_MAX_DISCORD_EVENTS_PER_CONNECTION)
                )
            )
            if overflow_ids:
                session.execute(
                    delete(DiscordConnectorEventRecord).where(
                        DiscordConnectorEventRecord.id.in_(overflow_ids)
                    )
                )
            session.commit()
            return inserted

    def list_discord_events(
        self,
        owner_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        connection_id: str | None = None,
        guild_id: str | None = None,
        level: str | None = None,
        event_type: str | None = None,
    ) -> tuple[list[DiscordConnectorEventRecord], int, int, int]:
        with self.database.session() as session:
            conditions = [DiscordConnectorEventRecord.owner_id == owner_id]
            if connection_id is not None:
                conditions.append(DiscordConnectorEventRecord.connection_id == connection_id)
            if guild_id is not None:
                conditions.append(DiscordConnectorEventRecord.guild_id == guild_id)
            if level is not None:
                conditions.append(DiscordConnectorEventRecord.level == level)
            if event_type is not None:
                conditions.append(DiscordConnectorEventRecord.event_type == event_type)

            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(DiscordConnectorEventRecord)
                    .where(*conditions)
                )
                or 0
            )
            pages = max(1, math.ceil(total / page_size))
            safe_page = min(max(page, 1), pages)
            records = list(
                session.scalars(
                    select(DiscordConnectorEventRecord)
                    .where(*conditions)
                    .order_by(
                        DiscordConnectorEventRecord.occurred_at.desc(),
                        DiscordConnectorEventRecord.id.desc(),
                    )
                    .offset((safe_page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return records, safe_page, total, pages

    def sync_discord_server_catalog(
''',
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "        with self.database.session() as session:\n            scope_result = session.execute(\n",
    "        with self.database.session() as session:\n"
    "            event_result = session.execute(\n"
    "                delete(DiscordConnectorEventRecord).where(\n"
    "                    DiscordConnectorEventRecord.owner_id == owner_id\n"
    "                )\n            )\n            scope_result = session.execute(\n",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "        return {\n            \"deployment_scopes\": int(getattr(scope_result, \"rowcount\", 0) or 0),",
    "        return {\n            \"discord_connector_events\": int(\n"
    "                getattr(event_result, \"rowcount\", 0) or 0\n            ),\n"
    "            \"deployment_scopes\": int(getattr(scope_result, \"rowcount\", 0) or 0),",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "        with self.database.session() as session:\n            connection_result = session.execute(\n",
    "        with self.database.session() as session:\n"
    "            event_result = session.execute(\n"
    "                update(DiscordConnectorEventRecord)\n"
    "                .where(DiscordConnectorEventRecord.owner_id == source_owner_id)\n"
    "                .values(owner_id=target_owner_id)\n            )\n"
    "            connection_result = session.execute(\n",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "        return {\n            \"connections\": int(getattr(connection_result, \"rowcount\", 0) or 0),\n"
    "            \"server_catalogs\": int(getattr(catalog_result, \"rowcount\", 0) or 0),",
    "        return {\n            \"discord_connector_events\": int(\n"
    "                getattr(event_result, \"rowcount\", 0) or 0\n            ),\n"
    "            \"connections\": int(getattr(connection_result, \"rowcount\", 0) or 0),\n"
    "            \"server_catalogs\": int(getattr(catalog_result, \"rowcount\", 0) or 0),",
)

# Persistence exports.
replace_once(
    "src/echo_masque/persistence/__init__.py",
    "    CharacterDeploymentRecord,\n    DiscordDeploymentScopeRecord,",
    "    CharacterDeploymentRecord,\n    DiscordConnectorEventRecord,\n"
    "    DiscordDeploymentScopeRecord,",
)
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '    "CharacterDeploymentRecord",\n    "Database",',
    '    "CharacterDeploymentRecord",\n    "Database",\n    "DiscordConnectorEventRecord",',
)

# Connector event API schemas.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    "from pydantic import BaseModel, Field",
    "from pydantic import BaseModel, ConfigDict, Field",
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    "class DiscordStickerContent(BaseModel):\n",
    '''class DiscordConnectorEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    level: Literal["info", "warning", "error"]
    event_type: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    guild_id: str = Field(default="", max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(default="", max_length=200)
    channel_name: str = Field(default="", max_length=160)
    thread_id: str = Field(default="", max_length=200)
    thread_name: str = Field(default="", max_length=160)
    source_message_id: str = Field(default="", max_length=200)
    deployment_id: str = Field(default="", max_length=64)
    character_name: str = Field(default="", max_length=160)
    details: dict[str, object] = Field(default_factory=dict, max_length=40)


class DiscordConnectorEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    events: list[DiscordConnectorEventItem] = Field(min_length=1, max_length=100)


class DiscordStickerContent(BaseModel):
''',
)

# Portal response schemas.
replace_once(
    "src/echo_masque/api/deployment_schemas.py",
    "    CharacterDeploymentRecord,\n    DiscordDeploymentScopeRecord,",
    "    CharacterDeploymentRecord,\n    DiscordConnectorEventRecord,\n"
    "    DiscordDeploymentScopeRecord,",
)
append_once(
    "src/echo_masque/api/deployment_schemas.py",
    "class DiscordConnectorLogPage(BaseModel):",
    '''
class DiscordConnectorLogView(BaseModel):
    id: str
    connection_id: str
    level: Literal["info", "warning", "error"]
    event_type: str
    message: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    thread_id: str
    thread_name: str
    source_message_id: str
    deployment_id: str
    character_name: str
    details: dict[str, object]
    occurred_at: datetime

    @classmethod
    def from_record(cls, record: DiscordConnectorEventRecord) -> "DiscordConnectorLogView":
        try:
            raw = json.loads(record.details_json)
        except json.JSONDecodeError:
            raw = {}
        details = raw if isinstance(raw, dict) else {}
        return cls(
            id=record.id,
            connection_id=record.connection_id,
            level=cast(Literal["info", "warning", "error"], record.level),
            event_type=record.event_type,
            message=record.message,
            guild_id=record.guild_id,
            guild_name=record.guild_name,
            channel_id=record.channel_id,
            channel_name=record.channel_name,
            thread_id=record.thread_id,
            thread_name=record.thread_name,
            source_message_id=record.source_message_id,
            deployment_id=record.deployment_id,
            character_name=record.character_name,
            details=cast(dict[str, object], details),
            occurred_at=record.occurred_at,
        )


class DiscordConnectorLogPage(BaseModel):
    items: list[DiscordConnectorLogView]
    page: int
    page_size: int
    total: int
    pages: int
''',
)

# Connector ingestion endpoint.
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    "    DiscordConnectorDeploymentView,\n    DiscordConnectorHeartbeat,",
    "    DiscordConnectorDeploymentView,\n    DiscordConnectorEventBatch,\n"
    "    DiscordConnectorHeartbeat,",
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '@router.post("/stickers/resolve", response_model=DiscordStickerContent)',
    '''@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
def record_connector_events(
    payload: DiscordConnectorEventBatch,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    try:
        deployment_repository(request).record_discord_events(
            connection_id=payload.connection_id,
            events=[item.model_dump() for item in payload.events],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stickers/resolve", response_model=DiscordStickerContent)''',
)

# Owner-scoped, server-filterable log endpoint.
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "    CharacterDeploymentView,\n    DiscordServerCatalogView,",
    "    CharacterDeploymentView,\n    DiscordConnectorLogPage,\n"
    "    DiscordConnectorLogView,\n    DiscordServerCatalogView,",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '@router.get("/deployments", response_model=list[CharacterDeploymentView])',
    '''@router.get("/discord/logs", response_model=DiscordConnectorLogPage)
def list_discord_logs(
    request: Request,
    user: CurrentUserDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    server_profile_id: str | None = Query(default=None, max_length=64),
    connection_id: str | None = Query(default=None, max_length=64),
    level: str | None = Query(default=None, pattern="^(info|warning|error)$"),
    event_type: str | None = Query(default=None, max_length=80),
) -> DiscordConnectorLogPage:
    repo = deployment_repository(request)
    guild_id: str | None = None
    resolved_connection_id = connection_id
    if server_profile_id is not None:
        profile = repo.get_server_profile(server_profile_id, user.id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Discord server profile not found.")
        if connection_id is not None and connection_id != profile.connection_id:
            raise HTTPException(status_code=409, detail="Server and connection filters conflict.")
        resolved_connection_id = profile.connection_id
        guild_id = profile.guild_id
    elif connection_id is not None:
        connection = repo.get_connection(connection_id, user.id)
        if connection is None or connection.platform != "discord":
            raise HTTPException(status_code=404, detail="Discord connection not found.")

    records, safe_page, total, pages = repo.list_discord_events(
        user.id,
        page=page,
        page_size=page_size,
        connection_id=resolved_connection_id,
        guild_id=guild_id,
        level=level,
        event_type=event_type,
    )
    return DiscordConnectorLogPage(
        items=[DiscordConnectorLogView.from_record(item) for item in records],
        page=safe_page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get("/deployments", response_model=list[CharacterDeploymentView])''',
)

# Connector types and client.
replace_once(
    "connectors/discord/src/types.ts",
    "export interface ConnectorHeartbeat {\n",
    '''export type DiscordConnectorEventLevel = "info" | "warning" | "error";

export interface DiscordConnectorEvent {
  id: string;
  occurred_at: string;
  level: DiscordConnectorEventLevel;
  event_type: string;
  message: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  source_message_id: string;
  deployment_id: string;
  character_name: string;
  details: Record<string, unknown>;
}

export interface DiscordConnectorEventBatch {
  connection_id: string;
  events: DiscordConnectorEvent[];
}

export interface ConnectorHeartbeat {
''',
)
replace_once(
    "connectors/discord/src/relayClient.ts",
    "  ConnectorHeartbeat,\n  DiscordInteractionClaim,",
    "  ConnectorHeartbeat,\n  DiscordConnectorEvent,\n"
    "  DiscordInteractionClaim,",
)
replace_once(
    "connectors/discord/src/relayClient.ts",
    "  async heartbeat(payload: Omit<ConnectorHeartbeat, \"connection_id\">): Promise<void> {",
    '''  async reportEvents(events: DiscordConnectorEvent[]): Promise<void> {
    if (!events.length) return;
    await this.request<void>("/api/connectors/discord/events", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, events })
    });
  }

  async heartbeat(payload: Omit<ConnectorHeartbeat, "connection_id">): Promise<void> {''',
)

# Discord Gateway instrumentation.
replace_once(
    "connectors/discord/src/index.ts",
    'import { ContextBuffer } from "./contextBuffer.js";\n',
    'import { ContextBuffer } from "./contextBuffer.js";\n'
    'import { DiscordEventReporter } from "./eventReporter.js";\n',
)
replace_once(
    "connectors/discord/src/index.ts",
    "const webhookManager = new DiscordWebhookManager(config.discordBotToken, relay);",
    "const webhookManager = new DiscordWebhookManager(config.discordBotToken, relay);\n"
    "const eventReporter = new DiscordEventReporter((events) => relay.reportEvents(events));\n"
    "eventReporter.start();",
)
replace_once(
    "connectors/discord/src/index.ts",
    "async function syncServerCatalog(): Promise<void> {",
    '''function reportDiscordEvent(input: {
  level: "info" | "warning" | "error";
  eventType: string;
  message: string;
  guildId?: string;
  guildName?: string;
  channelId?: string;
  channelName?: string;
  threadId?: string;
  threadName?: string;
  sourceMessageId?: string;
  deploymentId?: string;
  characterName?: string;
  details?: Record<string, unknown>;
}): void {
  eventReporter.record({
    level: input.level,
    event_type: input.eventType,
    message: input.message,
    guild_id: input.guildId ?? "",
    guild_name: input.guildName ?? "",
    channel_id: input.channelId ?? "",
    channel_name: input.channelName ?? "",
    thread_id: input.threadId ?? "",
    thread_name: input.threadName ?? "",
    source_message_id: input.sourceMessageId ?? "",
    deployment_id: input.deploymentId ?? "",
    character_name: input.characterName ?? "",
    details: input.details ?? {}
  });
}

async function syncServerCatalog(): Promise<void> {''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''  const guildMessage = message;
  const location = channelLocation(guildMessage);
  if (!location.channelId) return;
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
  if (!candidates.length) return;

  const originalText = normalizedText(guildMessage, botUser.id);
  const mentionedBot = guildMessage.mentions.users.has(botUser.id);
''',
    '''  const guildMessage = message;
  const location = channelLocation(guildMessage);
  if (!location.channelId) return;
  const originalText = normalizedText(guildMessage, botUser.id);
  const mentionedBot = guildMessage.mentions.users.has(botUser.id);
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
  if (mentionedBot) {
    reportDiscordEvent({
      level: "info",
      eventType: "mention_received",
      message: "Bot mention reached the Discord Gateway.",
      guildId: guildMessage.guildId,
      guildName: guildMessage.guild.name,
      channelId: location.channelId,
      channelName: location.channelName,
      threadId: location.threadId,
      threadName: location.threadName,
      sourceMessageId: guildMessage.id,
      details: {
        candidate_count: candidates.length,
        state_synchronized: stateSynchronized,
        has_readable_text: Boolean(originalText),
        sticker_count: guildMessage.stickers.size
      }
    });
  }
  if (!candidates.length) {
    if (mentionedBot) {
      reportDiscordEvent({
        level: "warning",
        eventType: "ignored_no_deployment",
        message: "The Tag was ignored because no active deployment matched this Server and Channel.",
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: guildMessage.id,
        details: { state_synchronized: stateSynchronized }
      });
    }
    return;
  }
''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    const audience = resolveAudience(
      candidates,
      originalText,
      replyTarget.deploymentId,
      config.groupAddressAliases
    );''',
    '''    if (replyTarget.characterMessage) {
      reportDiscordEvent({
        level: "info",
        eventType: "reply_received",
        message: "A reply to a Character Relay message reached the Discord Gateway.",
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: guildMessage.id,
        deploymentId: replyTarget.deploymentId ?? "",
        details: { candidate_count: candidates.length }
      });
    }
    const audience = resolveAudience(
      candidates,
      originalText,
      replyTarget.deploymentId,
      config.groupAddressAliases
    );''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    if (!audience.deployments.length) {
      if (
        audience.reason === "ambiguous" &&
        (mentionedBot || replyTarget.characterMessage)
      ) {
        await sendSelectionHelp(guildMessage, audience.options);
      }
      return;
    }''',
    '''    if (!audience.deployments.length) {
      if (mentionedBot || replyTarget.characterMessage) {
        reportDiscordEvent({
          level: "warning",
          eventType:
            audience.reason === "ambiguous" ? "audience_ambiguous" : "audience_not_found",
          message:
            audience.reason === "ambiguous"
              ? "The Tag reached the Connector, but multiple characters require explicit selection."
              : "The Tag reached the Connector, but no addressed character was found.",
          guildId: guildMessage.guildId,
          guildName: guildMessage.guild.name,
          channelId: location.channelId,
          channelName: location.channelName,
          threadId: location.threadId,
          threadName: location.threadName,
          sourceMessageId: guildMessage.id,
          details: {
            audience_reason: audience.reason,
            candidate_count: candidates.length,
            options: audience.options
          }
        });
      }
      if (
        audience.reason === "ambiguous" &&
        (mentionedBot || replyTarget.characterMessage)
      ) {
        await sendSelectionHelp(guildMessage, audience.options);
      }
      return;
    }''',
)
replace_once(
    "connectors/discord/src/index.ts",
    "    if (!eligibleDeployments.length) return;",
    '''    if (!eligibleDeployments.length) {
      if (mentionedBot || isReplyToCharacter) {
        reportDiscordEvent({
          level: "warning",
          eventType: "ignored_participation_mode",
          message: "The Tag matched a character, but its participation mode did not allow this trigger.",
          guildId: guildMessage.guildId,
          guildName: guildMessage.guild.name,
          channelId: location.channelId,
          channelName: location.channelName,
          threadId: location.threadId,
          threadName: location.threadName,
          sourceMessageId: guildMessage.id,
          details: {
            mentioned_bot: mentionedBot,
            replied_to_character: isReplyToCharacter,
            participation_modes: audience.deployments.map(
              (deployment) => deployment.participation_mode
            )
          }
        });
      }
      return;
    }''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {
      const deployment = resolveDeploymentLocation(baseDeployment, location);
      await guildMessage.channel.sendTyping();
      const reply = await relay.processMessage({''',
    '''    for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {
      const deployment = resolveDeploymentLocation(baseDeployment, location);
      reportDiscordEvent({
        level: "info",
        eventType: "runtime_started",
        message: "The Discord trigger matched a deployment and is entering Character Runtime.",
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: guildMessage.id,
        deploymentId: deployment.deployment_id,
        characterName: deploymentDisplayName(deployment),
        details: {
          audience_reason: audience.reason,
          response_index: responseIndex + 1,
          response_count: eligibleDeployments.length
        }
      });
      await guildMessage.channel.sendTyping();
      const reply = await relay.processMessage({''',
)
replace_last(
    "connectors/discord/src/index.ts",
    '      if (reply.action !== "reply" || !reply.text) continue;',
    '''      if (reply.action !== "reply" || !reply.text) {
        reportDiscordEvent({
          level: "info",
          eventType: "runtime_silent",
          message: "Character Runtime intentionally returned no Discord reply.",
          guildId: guildMessage.guildId,
          guildName: guildMessage.guild.name,
          channelId: location.channelId,
          channelName: location.channelName,
          threadId: location.threadId,
          threadName: location.threadName,
          sourceMessageId: guildMessage.id,
          deploymentId: deployment.deployment_id,
          characterName: deploymentDisplayName(deployment),
          details: {
            reason: reply.reason,
            latency_ms: reply.latency_ms ?? null,
            input_tokens: reply.input_tokens ?? null,
            output_tokens: reply.output_tokens ?? null
          }
        });
        continue;
      }''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      const sentMessageIds = await sendCharacterReply(
        guildMessage,
        deployment,
        outgoingText,
        botUser.id
      );''',
    '''      let sentMessageIds: string[];
      try {
        sentMessageIds = await sendCharacterReply(
          guildMessage,
          deployment,
          outgoingText,
          botUser.id
        );
      } catch (error) {
        reportDiscordEvent({
          level: "error",
          eventType: "delivery_error",
          message: "Character Runtime replied, but Discord delivery failed.",
          guildId: guildMessage.guildId,
          guildName: guildMessage.guild.name,
          channelId: location.channelId,
          channelName: location.channelName,
          threadId: location.threadId,
          threadName: location.threadName,
          sourceMessageId: guildMessage.id,
          deploymentId: deployment.deployment_id,
          characterName: deploymentDisplayName(deployment),
          details: { error: error instanceof Error ? error.message : String(error) }
        });
        throw error;
      }''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      log("Character reply sent to Discord.", {
        deploymentId: reply.deployment_id,''',
    '''      reportDiscordEvent({
        level: "info",
        eventType: "delivery_success",
        message: "Character reply was delivered to Discord.",
        guildId: guildMessage.guildId,
        guildName: guildMessage.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: guildMessage.id,
        deploymentId: deployment.deployment_id,
        characterName: deploymentDisplayName(deployment),
        details: {
          sent_message_ids: sentMessageIds,
          latency_ms: reply.latency_ms ?? null,
          identity_mode: deployment.identity_mode,
          webhook_status: deployment.webhook_status
        }
      });
      log("Character reply sent to Discord.", {
        deploymentId: reply.deployment_id,''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''client.on(Events.MessageCreate, (message) => {
  void processMessage(message).catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
    log("Discord message handler failed.", {
      messageId: message.id,
      error: lastError
    });
  });
});''',
    '''client.on(Events.MessageCreate, (message) => {
  void processMessage(message).catch((error: unknown) => {
    lastError = error instanceof Error ? error.message : String(error);
    if (message.inGuild()) {
      const location = channelLocation(message);
      reportDiscordEvent({
        level: "error",
        eventType: "handler_error",
        message: "Discord message processing failed before a reply could be delivered.",
        guildId: message.guildId,
        guildName: message.guild.name,
        channelId: location.channelId,
        channelName: location.channelName,
        threadId: location.threadId,
        threadName: location.threadName,
        sourceMessageId: message.id,
        details: { error: lastError }
      });
    }
    log("Discord message handler failed.", {
      messageId: message.id,
      error: lastError
    });
  });
});''',
)
replace_once(
    "connectors/discord/src/index.ts",
    "      last_error: lastError\n",
    "      last_error: lastError,\n"
    "      pending_portal_logs: eventReporter.pendingCount,\n"
    "      portal_log_last_error: eventReporter.lastError\n",
)
replace_once(
    "connectors/discord/src/index.ts",
    "  recoveryLoop?.stop();\n  if (heartbeatTimer) clearInterval(heartbeatTimer);",
    "  recoveryLoop?.stop();\n  await eventReporter.stop();\n"
    "  if (heartbeatTimer) clearInterval(heartbeatTimer);",
)

# Portal API types and request.
replace_once(
    "web/src/deploymentApi.ts",
    "export type ChannelScopeMode = \"exact\" | \"all_except\";\n",
    "export type ChannelScopeMode = \"exact\" | \"all_except\";\n"
    "export type DiscordConnectorLogLevel = \"info\" | \"warning\" | \"error\";\n",
)
replace_once(
    "web/src/deploymentApi.ts",
    "export interface CharacterDeployment {\n",
    '''export interface DiscordConnectorLog {
  id: string;
  connection_id: string;
  level: DiscordConnectorLogLevel;
  event_type: string;
  message: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  source_message_id: string;
  deployment_id: string;
  character_name: string;
  details: Record<string, unknown>;
  occurred_at: string;
}

export interface DiscordConnectorLogPage {
  items: DiscordConnectorLog[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface CharacterDeployment {
''',
)
replace_once(
    "web/src/deploymentApi.ts",
    "  listDeployments: (characterCardId?: string) =>",
    '''  listDiscordLogs: (options: {
    page?: number;
    pageSize?: number;
    serverProfileId?: string;
    connectionId?: string;
    level?: DiscordConnectorLogLevel | "all";
    eventType?: string;
  } = {}) => {
    const query = new URLSearchParams({
      page: String(options.page ?? 1),
      page_size: String(options.pageSize ?? 50)
    });
    if (options.serverProfileId) query.set("server_profile_id", options.serverProfileId);
    if (options.connectionId) query.set("connection_id", options.connectionId);
    if (options.level && options.level !== "all") query.set("level", options.level);
    if (options.eventType && options.eventType !== "all") {
      query.set("event_type", options.eventType);
    }
    return request<DiscordConnectorLogPage>(`/api/discord/logs?${query.toString()}`);
  },
  listDeployments: (characterCardId?: string) =>''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\n',
    'import { DiscordEventLogPanel } from "./DiscordEventLogPanel";\n'
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\n',
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
      {!demoMode && (
        <DiscordEventLogPanel
          profiles={serverProfiles}
          selectedServerProfileId={selectedServerProfileId}
          zh={zh}
        />
      )}
    </main>''',
)
replace_once(
    "web/src/main.tsx",
    'import "./discordServerProfiles.css";\n',
    'import "./discordEventLog.css";\nimport "./discordServerProfiles.css";\n',
)

# Remove temporary patch scaffolding from the validated commit.
(ROOT / ".github/apply_discord_portal_logs.py").unlink(missing_ok=True)
(ROOT / ".github/workflows/apply-discord-portal-logs.yml").unlink(missing_ok=True)
