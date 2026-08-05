from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("connectors/discord/railway.toml").write_text(
    '''[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "ALWAYS"
multiRegionConfig = { "us-west1" = { numReplicas = 0 }, "asia-southeast1-eqsg3a" = { numReplicas = 1 } }
''',
    encoding="utf-8",
)

Path("connectors/discord/src/eventReporter.ts").write_text(
    '''import { randomUUID } from "node:crypto";

import type { DiscordConnectorEvent } from "./types.js";

export type DiscordConnectorEventInput = Omit<
  DiscordConnectorEvent,
  "id" | "occurred_at"
>;

export type DiscordConnectorEventSink = (
  events: DiscordConnectorEvent[]
) => Promise<void>;

export class DiscordEventReporter {
  private readonly queue: DiscordConnectorEvent[] = [];
  private timer: NodeJS.Timeout | undefined;
  private flushing = false;
  private lastFailure: string | null = null;
  private lastSuccessfulFlushAt: string | null = null;
  private lastRecordedEventAt: string | null = null;
  private lastRecordedEventType: string | null = null;
  private sentEvents = 0;

  constructor(
    private readonly sink: DiscordConnectorEventSink,
    private readonly flushIntervalMs = 1_500,
    private readonly batchSize = 50,
    private readonly maximumPending = 1_000
  ) {}

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      void this.flush();
    }, this.flushIntervalMs);
  }

  record(event: DiscordConnectorEventInput): void {
    if (this.queue.length >= this.maximumPending) this.queue.shift();
    const occurredAt = new Date().toISOString();
    this.queue.push({
      id: randomUUID(),
      occurred_at: occurredAt,
      ...event
    });
    this.lastRecordedEventAt = occurredAt;
    this.lastRecordedEventType = event.event_type;
    if (this.queue.length >= this.batchSize) void this.flush();
  }

  async flush(): Promise<void> {
    if (this.flushing || !this.queue.length) return;
    this.flushing = true;
    const batch = this.queue.slice(0, this.batchSize);
    try {
      await this.sink(batch);
      this.queue.splice(0, batch.length);
      this.lastFailure = null;
      this.lastSuccessfulFlushAt = new Date().toISOString();
      this.sentEvents += batch.length;
    } catch (error) {
      this.lastFailure = error instanceof Error ? error.message : String(error);
    } finally {
      this.flushing = false;
    }
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    await this.flush();
  }

  get pendingCount(): number {
    return this.queue.length;
  }

  get lastError(): string | null {
    return this.lastFailure;
  }

  get lastSuccessAt(): string | null {
    return this.lastSuccessfulFlushAt;
  }

  get lastRecordedAt(): string | null {
    return this.lastRecordedEventAt;
  }

  get lastRecordedType(): string | null {
    return this.lastRecordedEventType;
  }

  get sentCount(): number {
    return this.sentEvents;
  }
}
''',
    encoding="utf-8",
)

replace(
    "connectors/discord/src/types.ts",
    '''export interface ConnectorHeartbeat {
  connection_id: string;
  bot_user_id: string;
  bot_display_name: string;
  status: "connected" | "offline" | "error";
  last_error: string;
  replica_region: string;
  gateway_ready: boolean;
  state_synchronized: boolean;
  visible_server_count: number;
}
''',
    '''export interface ConnectorHeartbeat {
  connection_id: string;
  bot_user_id: string;
  bot_display_name: string;
  status: "connected" | "offline" | "error";
  last_error: string;
  replica_region: string;
  replica_id: string;
  gateway_ready: boolean;
  state_synchronized: boolean;
  visible_server_count: number;
  event_log_pending_count: number;
  event_log_last_error: string;
  event_log_last_success_at: string;
  event_log_last_recorded_at: string;
  event_log_last_recorded_type: string;
  event_log_sent_count: number;
  last_gateway_message_at: string;
  last_gateway_message_id: string;
  last_gateway_mentioned_bot: boolean;
}
''',
)

replace(
    "connectors/discord/src/index.ts",
    '''let heartbeatTimer: NodeJS.Timeout | undefined;
let dedupeTimer: NodeJS.Timeout | undefined;
''',
    '''let heartbeatTimer: NodeJS.Timeout | undefined;
let dedupeTimer: NodeJS.Timeout | undefined;
let lastGatewayMessageAt: string | null = null;
let lastGatewayMessageId: string | null = null;
let lastGatewayMentionedBot = false;
''',
)

replace(
    "connectors/discord/src/index.ts",
    '''    last_error: error,
    replica_region: process.env.RAILWAY_REPLICA_REGION ?? "",
    gateway_ready: ready,
    state_synchronized: stateSynchronized,
    visible_server_count: client.guilds.cache.size
''',
    '''    last_error: error,
    replica_region: process.env.RAILWAY_REPLICA_REGION ?? "",
    replica_id: process.env.RAILWAY_REPLICA_ID ?? "",
    gateway_ready: ready,
    state_synchronized: stateSynchronized,
    visible_server_count: client.guilds.cache.size,
    event_log_pending_count: eventReporter.pendingCount,
    event_log_last_error: eventReporter.lastError ?? "",
    event_log_last_success_at: eventReporter.lastSuccessAt ?? "",
    event_log_last_recorded_at: eventReporter.lastRecordedAt ?? "",
    event_log_last_recorded_type: eventReporter.lastRecordedType ?? "",
    event_log_sent_count: eventReporter.sentCount,
    last_gateway_message_at: lastGatewayMessageAt ?? "",
    last_gateway_message_id: lastGatewayMessageId ?? "",
    last_gateway_mentioned_bot: lastGatewayMentionedBot
''',
)

replace(
    "connectors/discord/src/index.ts",
    '''  const originalText = normalizedText(guildMessage, botUser.id);
  const mentionedBot = guildMessage.mentions.users.has(botUser.id);
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
  if (mentionedBot) {
''',
    '''  const originalText = normalizedText(guildMessage, botUser.id);
  const mentionedBot = guildMessage.mentions.users.has(botUser.id);
  lastGatewayMessageAt = new Date().toISOString();
  lastGatewayMessageId = guildMessage.id;
  lastGatewayMentionedBot = mentionedBot;
  const candidates = deploymentsFor(
    deployments,
    location.channelId,
    location.threadId,
    guildMessage.guildId,
    location.categoryId
  );
  reportDiscordEvent({
    level: "info",
    eventType: "message_received",
    message: "A Discord message reached the Gateway message handler.",
    guildId: guildMessage.guildId,
    guildName: guildMessage.guild.name,
    channelId: location.channelId,
    channelName: location.channelName,
    threadId: location.threadId,
    threadName: location.threadName,
    sourceMessageId: guildMessage.id,
    details: {
      mentioned_bot: mentionedBot,
      candidate_count: candidates.length,
      has_readable_text: Boolean(originalText),
      sticker_count: guildMessage.stickers.size
    }
  });
  if (mentionedBot) {
''',
)

replace(
    "src/echo_masque/api/connector_schemas.py",
    '''    replica_region: str = Field(default="", max_length=120)
    gateway_ready: bool = False
    state_synchronized: bool = False
    visible_server_count: int = Field(default=0, ge=0, le=10000)
''',
    '''    replica_region: str = Field(default="", max_length=120)
    replica_id: str = Field(default="", max_length=200)
    gateway_ready: bool = False
    state_synchronized: bool = False
    visible_server_count: int = Field(default=0, ge=0, le=10000)
    event_log_pending_count: int = Field(default=0, ge=0, le=10000)
    event_log_last_error: str = Field(default="", max_length=2000)
    event_log_last_success_at: str = Field(default="", max_length=64)
    event_log_last_recorded_at: str = Field(default="", max_length=64)
    event_log_last_recorded_type: str = Field(default="", max_length=80)
    event_log_sent_count: int = Field(default=0, ge=0)
    last_gateway_message_at: str = Field(default="", max_length=64)
    last_gateway_message_id: str = Field(default="", max_length=200)
    last_gateway_mentioned_bot: bool = False
''',
)

replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''        replica_region: str = "",
        gateway_ready: bool = False,
        state_synchronized: bool = False,
        visible_server_count: int = 0,
    ) -> bool:
''',
    '''        replica_region: str = "",
        replica_id: str = "",
        gateway_ready: bool = False,
        state_synchronized: bool = False,
        visible_server_count: int = 0,
        event_log_pending_count: int = 0,
        event_log_last_error: str = "",
        event_log_last_success_at: str = "",
        event_log_last_recorded_at: str = "",
        event_log_last_recorded_type: str = "",
        event_log_sent_count: int = 0,
        last_gateway_message_at: str = "",
        last_gateway_message_id: str = "",
        last_gateway_mentioned_bot: bool = False,
    ) -> bool:
''',
)

replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            metadata["replica_region"] = replica_region
            metadata["gateway_ready"] = gateway_ready
            metadata["state_synchronized"] = state_synchronized
            metadata["visible_server_count"] = visible_server_count
''',
    '''            metadata["replica_region"] = replica_region
            metadata["replica_id"] = replica_id
            metadata["gateway_ready"] = gateway_ready
            metadata["state_synchronized"] = state_synchronized
            metadata["visible_server_count"] = visible_server_count
            metadata["event_log_pending_count"] = event_log_pending_count
            metadata["event_log_last_error"] = event_log_last_error
            metadata["event_log_last_success_at"] = event_log_last_success_at
            metadata["event_log_last_recorded_at"] = event_log_last_recorded_at
            metadata["event_log_last_recorded_type"] = event_log_last_recorded_type
            metadata["event_log_sent_count"] = event_log_sent_count
            metadata["last_gateway_message_at"] = last_gateway_message_at
            metadata["last_gateway_message_id"] = last_gateway_message_id
            metadata["last_gateway_mentioned_bot"] = last_gateway_mentioned_bot
''',
)

replace(
    "src/echo_masque/api/routes/connectors.py",
    '''        replica_region=payload.replica_region,
        gateway_ready=payload.gateway_ready,
        state_synchronized=payload.state_synchronized,
        visible_server_count=payload.visible_server_count,
''',
    '''        replica_region=payload.replica_region,
        replica_id=payload.replica_id,
        gateway_ready=payload.gateway_ready,
        state_synchronized=payload.state_synchronized,
        visible_server_count=payload.visible_server_count,
        event_log_pending_count=payload.event_log_pending_count,
        event_log_last_error=payload.event_log_last_error,
        event_log_last_success_at=payload.event_log_last_success_at,
        event_log_last_recorded_at=payload.event_log_last_recorded_at,
        event_log_last_recorded_type=payload.event_log_last_recorded_type,
        event_log_sent_count=payload.event_log_sent_count,
        last_gateway_message_at=payload.last_gateway_message_at,
        last_gateway_message_id=payload.last_gateway_message_id,
        last_gateway_mentioned_bot=payload.last_gateway_mentioned_bot,
''',
)

replace(
    "tests/test_discord_connector.py",
    '''            "replica_region": "asia-southeast1-eqsg3a",
            "gateway_ready": True,
            "state_synchronized": True,
            "visible_server_count": 2,
''',
    '''            "replica_region": "asia-southeast1-eqsg3a",
            "replica_id": "replica-singapore-1",
            "gateway_ready": True,
            "state_synchronized": True,
            "visible_server_count": 2,
            "event_log_pending_count": 3,
            "event_log_last_error": "HTTP 422 from /events",
            "event_log_last_success_at": "2026-08-05T13:00:00.000Z",
            "event_log_last_recorded_at": "2026-08-05T13:00:20.000Z",
            "event_log_last_recorded_type": "mention_received",
            "event_log_sent_count": 12,
            "last_gateway_message_at": "2026-08-05T13:00:20.000Z",
            "last_gateway_message_id": "discord-message-123",
            "last_gateway_mentioned_bot": True,
''',
)

replace(
    "tests/test_discord_connector.py",
    '''    assert updated["metadata"]["replica_region"] == "asia-southeast1-eqsg3a"
    assert updated["metadata"]["gateway_ready"] is True
    assert updated["metadata"]["state_synchronized"] is True
    assert updated["metadata"]["visible_server_count"] == 2
''',
    '''    assert updated["metadata"]["replica_region"] == "asia-southeast1-eqsg3a"
    assert updated["metadata"]["replica_id"] == "replica-singapore-1"
    assert updated["metadata"]["gateway_ready"] is True
    assert updated["metadata"]["state_synchronized"] is True
    assert updated["metadata"]["visible_server_count"] == 2
    assert updated["metadata"]["event_log_pending_count"] == 3
    assert updated["metadata"]["event_log_last_error"] == "HTTP 422 from /events"
    assert updated["metadata"]["event_log_last_success_at"] == "2026-08-05T13:00:00.000Z"
    assert updated["metadata"]["event_log_last_recorded_at"] == "2026-08-05T13:00:20.000Z"
    assert updated["metadata"]["event_log_last_recorded_type"] == "mention_received"
    assert updated["metadata"]["event_log_sent_count"] == 12
    assert updated["metadata"]["last_gateway_message_at"] == "2026-08-05T13:00:20.000Z"
    assert updated["metadata"]["last_gateway_message_id"] == "discord-message-123"
    assert updated["metadata"]["last_gateway_mentioned_bot"] is True
''',
)

replace(
    "connectors/discord/src/eventReporter.test.ts",
    '''    await reporter.flush();
    expect(reporter.pendingCount).toBe(0);
    expect(reporter.lastError).toBeNull();
    expect(delivered).toHaveLength(2);
''',
    '''    await reporter.flush();
    expect(reporter.pendingCount).toBe(0);
    expect(reporter.lastError).toBeNull();
    expect(reporter.lastSuccessAt).not.toBeNull();
    expect(reporter.lastRecordedAt).not.toBeNull();
    expect(reporter.lastRecordedType).toBe("ignored_no_deployment");
    expect(reporter.sentCount).toBe(2);
    expect(delivered).toHaveLength(2);
''',
)

replace(
    "web/src/discordServerStatus.ts",
    '''  replicaRegion: string;
  connectorDisplayName: string;
  lastError: string;
  gatewayReady: boolean | null;
  stateSynchronized: boolean | null;
  visibleServerCount: number | null;
''',
    '''  replicaRegion: string;
  replicaId: string;
  connectorDisplayName: string;
  lastError: string;
  gatewayReady: boolean | null;
  stateSynchronized: boolean | null;
  visibleServerCount: number | null;
  eventLogPendingCount: number | null;
  eventLogLastError: string;
  eventLogLastSuccessAt: string;
  eventLogLastRecordedAt: string;
  eventLogLastRecordedType: string;
  eventLogSentCount: number | null;
  lastGatewayMessageAt: string;
  lastGatewayMessageId: string;
  lastGatewayMentionedBot: boolean | null;
''',
)

replace(
    "web/src/discordServerStatus.ts",
    '''      replicaRegion: metadataString(connection, "replica_region"),
      connectorDisplayName: metadataString(connection, "connector_display_name"),
      lastError: metadataString(connection, "last_error"),
      gatewayReady: metadataBoolean(connection, "gateway_ready"),
      stateSynchronized: metadataBoolean(connection, "state_synchronized"),
      visibleServerCount: metadataNumber(connection, "visible_server_count")
''',
    '''      replicaRegion: metadataString(connection, "replica_region"),
      replicaId: metadataString(connection, "replica_id"),
      connectorDisplayName: metadataString(connection, "connector_display_name"),
      lastError: metadataString(connection, "last_error"),
      gatewayReady: metadataBoolean(connection, "gateway_ready"),
      stateSynchronized: metadataBoolean(connection, "state_synchronized"),
      visibleServerCount: metadataNumber(connection, "visible_server_count"),
      eventLogPendingCount: metadataNumber(connection, "event_log_pending_count"),
      eventLogLastError: metadataString(connection, "event_log_last_error"),
      eventLogLastSuccessAt: metadataString(connection, "event_log_last_success_at"),
      eventLogLastRecordedAt: metadataString(connection, "event_log_last_recorded_at"),
      eventLogLastRecordedType: metadataString(connection, "event_log_last_recorded_type"),
      eventLogSentCount: metadataNumber(connection, "event_log_sent_count"),
      lastGatewayMessageAt: metadataString(connection, "last_gateway_message_at"),
      lastGatewayMessageId: metadataString(connection, "last_gateway_message_id"),
      lastGatewayMentionedBot: metadataBoolean(connection, "last_gateway_mentioned_bot")
''',
)

replace(
    "web/src/discordServerStatus.test.ts",
    '''      replica_region: "asia-southeast1-eqsg3a",
      gateway_ready: true,
      state_synchronized: true,
      visible_server_count: 2
''',
    '''      replica_region: "asia-southeast1-eqsg3a",
      replica_id: "replica-sg-1",
      gateway_ready: true,
      state_synchronized: true,
      visible_server_count: 2,
      event_log_pending_count: 1,
      event_log_last_error: "HTTP 422",
      event_log_last_success_at: "2026-08-05T12:59:10Z",
      event_log_last_recorded_at: "2026-08-05T12:59:20Z",
      event_log_last_recorded_type: "mention_received",
      event_log_sent_count: 7,
      last_gateway_message_at: "2026-08-05T12:59:20Z",
      last_gateway_message_id: "message-1",
      last_gateway_mentioned_bot: true
''',
)

replace(
    "web/src/discordServerStatus.test.ts",
    '''    expect(result?.state).toBe("connected");
    expect(result?.replicaRegion).toBe("asia-southeast1-eqsg3a");
''',
    '''    expect(result?.state).toBe("connected");
    expect(result?.replicaRegion).toBe("asia-southeast1-eqsg3a");
    expect(result?.replicaId).toBe("replica-sg-1");
    expect(result?.eventLogPendingCount).toBe(1);
    expect(result?.eventLogLastError).toBe("HTTP 422");
    expect(result?.eventLogLastRecordedType).toBe("mention_received");
    expect(result?.lastGatewayMentionedBot).toBe(true);
''',
)

replace(
    "web/src/DiscordEventLogPanel.tsx",
    '''const EVENT_TYPES = [
  "mention_received",
''',
    '''const EVENT_TYPES = [
  "message_received",
  "mention_received",
''',
)

replace(
    "web/src/DiscordEventLogPanel.tsx",
    '''const EVENT_LABELS: Record<string, { en: string; zh: string }> = {
  mention_received: { en: "Bot mention received", zh: "收到 Bot Tag" },
''',
    '''const EVENT_LABELS: Record<string, { en: string; zh: string }> = {
  message_received: { en: "Gateway message received", zh: "Gateway 收到消息" },
  mention_received: { en: "Bot mention received", zh: "收到 Bot Tag" },
''',
)

replace(
    "web/src/DiscordEventLogPanel.tsx",
    '''                  <div>
                    <dt>{zh ? "Replica Region" : "Replica region"}</dt>
                    <dd>{item.replicaRegion || (zh ? "未上报" : "Not reported")}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Gateway Ready" : "Gateway ready"}</dt>
''',
    '''                  <div>
                    <dt>{zh ? "Replica Region" : "Replica region"}</dt>
                    <dd>{item.replicaRegion || (zh ? "未上报" : "Not reported")}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Replica ID" : "Replica ID"}</dt>
                    <dd>{item.replicaId || (zh ? "未上报" : "Not reported")}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Gateway Ready" : "Gateway ready"}</dt>
''',
)

replace(
    "web/src/DiscordEventLogPanel.tsx",
    '''                  <div>
                    <dt>{zh ? "可见 Channel" : "Visible channels"}</dt>
                    <dd>{item.catalog?.channels.length ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Server ID</dt>
                    <dd>{item.profile.guild_id}</dd>
                  </div>
                </dl>
                {item.lastError && (
''',
    '''                  <div>
                    <dt>{zh ? "可见 Channel" : "Visible channels"}</dt>
                    <dd>{item.catalog?.channels.length ?? 0}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "最后 Gateway 消息" : "Last Gateway message"}</dt>
                    <dd>{formatTime(item.lastGatewayMessageAt)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "最后消息有 Tag Bot" : "Last message mentioned Bot"}</dt>
                    <dd>{booleanValue(item.lastGatewayMentionedBot, zh)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Reporter 待上传" : "Reporter pending"}</dt>
                    <dd>{item.eventLogPendingCount ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Reporter 最后捕获" : "Reporter last captured"}</dt>
                    <dd>
                      {formatTime(item.eventLogLastRecordedAt)}
                      {item.eventLogLastRecordedType && ` · ${item.eventLogLastRecordedType}`}
                    </dd>
                  </div>
                  <div>
                    <dt>{zh ? "Reporter 最后上传成功" : "Reporter last upload"}</dt>
                    <dd>{formatTime(item.eventLogLastSuccessAt)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Reporter 已上传" : "Reporter sent"}</dt>
                    <dd>{item.eventLogSentCount ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Server ID</dt>
                    <dd>{item.profile.guild_id}</dd>
                  </div>
                </dl>
                {item.eventLogLastError && (
                  <p className="discord-server-last-error">
                    <strong>{zh ? "Event Log error：" : "Event Log error: "}</strong>
                    {item.eventLogLastError}
                  </p>
                )}
                {item.lastError && (
''',
)
