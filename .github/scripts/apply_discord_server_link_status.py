from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "connectors/discord/src/types.ts",
    '''export interface ConnectorHeartbeat {
  connection_id: string;
  bot_user_id: string;
  bot_display_name: string;
  status: "connected" | "offline" | "error";
  last_error: string;
}
''',
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
)

replace(
    "connectors/discord/src/index.ts",
    '''  await relay.heartbeat({
    bot_user_id: user.id,
    bot_display_name: user.tag,
    status,
    last_error: error
  });
''',
    '''  await relay.heartbeat({
    bot_user_id: user.id,
    bot_display_name: user.tag,
    status,
    last_error: error,
    replica_region: process.env.RAILWAY_REPLICA_REGION ?? "",
    gateway_ready: ready,
    state_synchronized: stateSynchronized,
    visible_server_count: client.guilds.cache.size
  });
''',
)

replace(
    "src/echo_masque/api/connector_schemas.py",
    '''class DiscordConnectorHeartbeat(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    bot_user_id: str = Field(min_length=1, max_length=200)
    bot_display_name: str = Field(min_length=1, max_length=120)
    status: DiscordConnectionStatus = "connected"
    last_error: str = Field(default="", max_length=2000)
''',
    '''class DiscordConnectorHeartbeat(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    bot_user_id: str = Field(min_length=1, max_length=200)
    bot_display_name: str = Field(min_length=1, max_length=120)
    status: DiscordConnectionStatus = "connected"
    last_error: str = Field(default="", max_length=2000)
    replica_region: str = Field(default="", max_length=120)
    gateway_ready: bool = False
    state_synchronized: bool = False
    visible_server_count: int = Field(default=0, ge=0, le=10000)
''',
)

replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''        display_name: str,
        status: str,
        last_error: str,
    ) -> bool:
''',
    '''        display_name: str,
        status: str,
        last_error: str,
        replica_region: str,
        gateway_ready: bool,
        state_synchronized: bool,
        visible_server_count: int,
    ) -> bool:
''',
)

replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            metadata["last_error"] = last_error
            metadata["heartbeat_source"] = f"{platform}_connector"
            metadata["connector_display_name"] = display_name
''',
    '''            metadata["last_error"] = last_error
            metadata["heartbeat_source"] = f"{platform}_connector"
            metadata["connector_display_name"] = display_name
            metadata["replica_region"] = replica_region
            metadata["gateway_ready"] = gateway_ready
            metadata["state_synchronized"] = state_synchronized
            metadata["visible_server_count"] = visible_server_count
''',
)

replace(
    "src/echo_masque/api/routes/connectors.py",
    '''        display_name=payload.bot_display_name,
        status=payload.status,
        last_error=payload.last_error,
    )
''',
    '''        display_name=payload.bot_display_name,
        status=payload.status,
        last_error=payload.last_error,
        replica_region=payload.replica_region,
        gateway_ready=payload.gateway_ready,
        state_synchronized=payload.state_synchronized,
        visible_server_count=payload.visible_server_count,
    )
''',
)

status_source = r'''import type {
  DiscordServerCatalog,
  DiscordServerProfile,
  PlatformConnection
} from "./deploymentApi";

export type DiscordServerLinkState =
  | "connected"
  | "stale"
  | "connector_error"
  | "connector_offline"
  | "server_not_seen";

export interface DiscordServerLinkStatus {
  profile: DiscordServerProfile;
  connection: PlatformConnection | null;
  catalog: DiscordServerCatalog | null;
  state: DiscordServerLinkState;
  heartbeatFresh: boolean;
  catalogFresh: boolean;
  replicaRegion: string;
  connectorDisplayName: string;
  lastError: string;
  gatewayReady: boolean | null;
  stateSynchronized: boolean | null;
  visibleServerCount: number | null;
}

export const SERVER_LINK_FRESHNESS_MS = 120_000;

function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fresh(value: string | null | undefined, now: number): boolean {
  const parsed = timestamp(value);
  return parsed !== null && now - parsed <= SERVER_LINK_FRESHNESS_MS;
}

function metadataString(
  connection: PlatformConnection | null,
  key: string
): string {
  const value = connection?.metadata[key];
  return typeof value === "string" ? value : "";
}

function metadataBoolean(
  connection: PlatformConnection | null,
  key: string
): boolean | null {
  const value = connection?.metadata[key];
  return typeof value === "boolean" ? value : null;
}

function metadataNumber(
  connection: PlatformConnection | null,
  key: string
): number | null {
  const value = connection?.metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function buildDiscordServerStatuses(
  profiles: DiscordServerProfile[],
  connections: PlatformConnection[],
  catalogs: DiscordServerCatalog[],
  now = Date.now()
): DiscordServerLinkStatus[] {
  const connectionMap = new Map(connections.map((item) => [item.id, item]));
  const catalogMap = new Map(
    catalogs.map((item) => [`${item.connection_id}:${item.guild_id}`, item])
  );

  return profiles.map((profile) => {
    const connection = connectionMap.get(profile.connection_id) ?? null;
    const catalog =
      catalogMap.get(`${profile.connection_id}:${profile.guild_id}`) ?? null;
    const heartbeatFresh = fresh(connection?.last_seen_at, now);
    const catalogFresh = fresh(catalog?.synced_at, now);

    let state: DiscordServerLinkState;
    if (!connection || connection.status === "offline" || connection.status === "disconnected") {
      state = "connector_offline";
    } else if (connection.status === "error") {
      state = "connector_error";
    } else if (!heartbeatFresh) {
      state = "stale";
    } else if (!catalog) {
      state = "server_not_seen";
    } else if (!catalogFresh) {
      state = "stale";
    } else {
      state = "connected";
    }

    return {
      profile,
      connection,
      catalog,
      state,
      heartbeatFresh,
      catalogFresh,
      replicaRegion: metadataString(connection, "replica_region"),
      connectorDisplayName: metadataString(connection, "connector_display_name"),
      lastError: metadataString(connection, "last_error"),
      gatewayReady: metadataBoolean(connection, "gateway_ready"),
      stateSynchronized: metadataBoolean(connection, "state_synchronized"),
      visibleServerCount: metadataNumber(connection, "visible_server_count")
    };
  });
}
'''
Path("web/src/discordServerStatus.ts").write_text(status_source, encoding="utf-8")

status_test = r'''import { describe, expect, it } from "vitest";

import type {
  DiscordServerCatalog,
  DiscordServerProfile,
  PlatformConnection
} from "./deploymentApi";
import { buildDiscordServerStatuses } from "./discordServerStatus";

const NOW = Date.parse("2026-08-05T13:00:00Z");

function connection(
  status: PlatformConnection["status"],
  lastSeenAt = "2026-08-05T12:59:30Z"
): PlatformConnection {
  return {
    id: "connection-1",
    platform: "discord",
    display_name: "Character Relay Discord",
    connection_mode: "managed",
    external_account_id: "bot-1",
    status,
    metadata: {
      connector_display_name: "CharacterRelayBot#0001",
      replica_region: "asia-southeast1-eqsg3a",
      gateway_ready: true,
      state_synchronized: true,
      visible_server_count: 2
    },
    last_seen_at: lastSeenAt,
    created_at: "2026-08-05T12:00:00Z",
    updated_at: "2026-08-05T12:59:30Z"
  };
}

const profile: DiscordServerProfile = {
  id: "profile-1",
  connection_id: "connection-1",
  name: "Test server",
  guild_id: "guild-1",
  guild_name: "Guild One",
  channel_scope_mode: "all_except",
  excluded_channel_ids: [],
  excluded_category_ids: [],
  thread_policy: "inherit_parent",
  created_at: "2026-08-05T12:00:00Z",
  updated_at: "2026-08-05T12:00:00Z"
};

const catalog: DiscordServerCatalog = {
  connection_id: "connection-1",
  guild_id: "guild-1",
  guild_name: "Guild One",
  channels: [],
  synced_at: "2026-08-05T12:59:20Z"
};

describe("buildDiscordServerStatuses", () => {
  it("reports a fresh heartbeat and catalog as connected", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected")],
      [catalog],
      NOW
    );
    expect(result?.state).toBe("connected");
    expect(result?.replicaRegion).toBe("asia-southeast1-eqsg3a");
  });

  it("reports a live connector that cannot see a configured server", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected")],
      [],
      NOW
    );
    expect(result?.state).toBe("server_not_seen");
  });

  it("reports stale heartbeat data", () => {
    const [result] = buildDiscordServerStatuses(
      [profile],
      [connection("connected", "2026-08-05T12:50:00Z")],
      [catalog],
      NOW
    );
    expect(result?.state).toBe("stale");
  });

  it("preserves explicit connector error and offline states", () => {
    expect(
      buildDiscordServerStatuses([profile], [connection("error")], [catalog], NOW)[0]
        ?.state
    ).toBe("connector_error");
    expect(
      buildDiscordServerStatuses(
        [profile],
        [connection("disconnected")],
        [catalog],
        NOW
      )[0]?.state
    ).toBe("connector_offline");
  });
});
'''
Path("web/src/discordServerStatus.test.ts").write_text(status_test, encoding="utf-8")

panel_source = r'''import { useCallback, useEffect, useMemo, useState } from "react";

import {
  deploymentApi,
  type DiscordConnectorLog,
  type DiscordConnectorLogLevel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type PlatformConnection
} from "./deploymentApi";
import {
  buildDiscordServerStatuses,
  type DiscordServerLinkState
} from "./discordServerStatus";
import { Pagination } from "./Pagination";

interface Props {
  profiles: DiscordServerProfile[];
  selectedServerProfileId: string;
  zh: boolean;
}

const EVENT_TYPES = [
  "mention_received",
  "reply_received",
  "ignored_no_deployment",
  "audience_ambiguous",
  "audience_not_found",
  "ignored_participation_mode",
  "runtime_started",
  "runtime_silent",
  "delivery_success",
  "delivery_error",
  "handler_error"
] as const;

const EVENT_LABELS: Record<string, { en: string; zh: string }> = {
  mention_received: { en: "Bot mention received", zh: "收到 Bot Tag" },
  reply_received: { en: "Character reply received", zh: "收到角色回复触发" },
  ignored_no_deployment: { en: "No matching deployment", zh: "没有命中部署" },
  audience_ambiguous: { en: "Character selection required", zh: "角色选择不明确" },
  audience_not_found: { en: "Character not found", zh: "没有找到指定角色" },
  ignored_participation_mode: { en: "Blocked by participation mode", zh: "参与模式未允许" },
  runtime_started: { en: "Runtime request started", zh: "开始调用角色 Runtime" },
  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },
  delivery_success: { en: "Reply delivered", zh: "回复发送成功" },
  delivery_error: { en: "Reply delivery failed", zh: "回复发送失败" },
  handler_error: { en: "Message handler failed", zh: "消息处理失败" }
};

const LINK_LABELS: Record<DiscordServerLinkState, { en: string; zh: string }> = {
  connected: { en: "Connected", zh: "已连接" },
  stale: { en: "Status stale", zh: "状态已过期" },
  connector_error: { en: "Connector error", zh: "Connector 错误" },
  connector_offline: { en: "Connector offline", zh: "Connector 离线" },
  server_not_seen: { en: "Server not seen", zh: "未发现该 Server" }
};

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(parsed);
}

function labelEvent(value: string, zh: boolean): string {
  const label = EVENT_LABELS[value];
  return label ? (zh ? label.zh : label.en) : value.replaceAll("_", " ");
}

function statusDiagnosis(state: DiscordServerLinkState, zh: boolean): string {
  const messages: Record<DiscordServerLinkState, { en: string; zh: string }> = {
    connected: {
      en: "The Gateway heartbeat and this Server catalog are both current.",
      zh: "Gateway 心跳与该 Server Catalog 都在持续更新。"
    },
    stale: {
      en: "No current heartbeat or Server catalog update was received within two minutes.",
      zh: "两分钟内没有收到新的心跳或 Server Catalog 更新。"
    },
    connector_error: {
      en: "The Connector reported an error. Check the last error below.",
      zh: "Connector 主动报告了错误，请查看下方 Last error。"
    },
    connector_offline: {
      en: "The Portal is not receiving Connector heartbeats.",
      zh: "Portal 没有收到 Connector 心跳。"
    },
    server_not_seen: {
      en: "The Connector is alive, but the Bot did not report this Server. The Bot may have been removed or lacks View Channels permission.",
      zh: "Connector 在线，但 Bot 没有上报该 Server。Bot 可能未加入、已被移除，或缺少 View Channels 权限。"
    }
  };
  return zh ? messages[state].zh : messages[state].en;
}

function booleanValue(value: boolean | null, zh: boolean): string {
  if (value === null) return zh ? "未上报" : "Not reported";
  if (value) return zh ? "是" : "Yes";
  return zh ? "否" : "No";
}

export function DiscordEventLogPanel({
  profiles,
  selectedServerProfileId,
  zh
}: Props) {
  const [serverProfileId, setServerProfileId] = useState(selectedServerProfileId || "all");
  const [level, setLevel] = useState<"all" | DiscordConnectorLogLevel>("all");
  const [eventType, setEventType] = useState("all");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<DiscordConnectorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [catalog, setCatalog] = useState<DiscordServerCatalog[]>([]);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedServerProfileId) setServerProfileId(selectedServerProfileId);
  }, [selectedServerProfileId]);

  const load = useCallback(async () => {
    try {
      const result = await deploymentApi.listDiscordLogs({
        page,
        pageSize: 50,
        serverProfileId: serverProfileId === "all" ? undefined : serverProfileId,
        level,
        eventType
      });
      setItems(result.items);
      setPage(result.page);
      setPages(result.pages);
      setTotal(result.total);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [eventType, level, page, serverProfileId]);

  const loadStatus = useCallback(async () => {
    try {
      const [nextConnections, nextCatalog] = await Promise.all([
        deploymentApi.listConnections(),
        deploymentApi.listDiscordServerCatalog()
      ]);
      setConnections(nextConnections);
      setCatalog(nextCatalog);
      setStatusError(null);
    } catch (reason) {
      setStatusError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const serverStatuses = useMemo(() => {
    const statuses = buildDiscordServerStatuses(profiles, connections, catalog);
    return statuses.sort((left, right) => {
      if (left.profile.id === selectedServerProfileId) return -1;
      if (right.profile.id === selectedServerProfileId) return 1;
      return left.profile.guild_name.localeCompare(right.profile.guild_name);
    });
  }, [catalog, connections, profiles, selectedServerProfileId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    setStatusLoading(true);
    void loadStatus();
    const timer = window.setInterval(() => void loadStatus(), 10_000);
    return () => window.clearInterval(timer);
  }, [loadStatus]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void load(), 5_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load]);

  function changeFilter(setter: (value: string) => void, value: string) {
    setter(value);
    setPage(1);
  }

  return (
    <section className="paper-sheet discord-event-log-panel">
      <section className="discord-server-status-section">
        <div className="panel-heading-row discord-server-status-heading">
          <div>
            <p className="tape-label">SERVER CONNECTION STATUS</p>
            <h2>{zh ? "Discord Server 连接状态" : "Discord server connection status"}</h2>
            <p>
              {zh
                ? "独立检查 Connector 心跳、Discord Gateway、Singapore Replica 与 Bot 实际看到的 Server Catalog。"
                : "Independently checks Connector heartbeat, Discord Gateway, Railway replica region, and the Server catalog actually visible to the Bot."}
            </p>
          </div>
          <button
            className="paper-button"
            onClick={() => void loadStatus()}
            disabled={statusLoading}
          >
            {statusLoading ? (zh ? "检查中…" : "Checking…") : zh ? "检查连接" : "Check status"}
          </button>
        </div>

        {statusError && <p className="error-note">{statusError}</p>}

        <div className="discord-server-status-grid">
          {serverStatuses.map((item) => {
            const selected = item.profile.id === selectedServerProfileId;
            const connection = item.connection;
            return (
              <article
                className={`discord-server-status-card server-link-${item.state}${
                  selected ? " is-selected" : ""
                }`}
                key={item.profile.id}
              >
                <div className="discord-server-status-title">
                  <div>
                    <strong>{item.profile.guild_name}</strong>
                    <small>{item.profile.name}</small>
                  </div>
                  <span className={`server-link-badge server-link-${item.state}`}>
                    {zh ? LINK_LABELS[item.state].zh : LINK_LABELS[item.state].en}
                  </span>
                </div>
                <p>{statusDiagnosis(item.state, zh)}</p>
                <dl className="discord-server-status-details">
                  <div>
                    <dt>{zh ? "Connector" : "Connector"}</dt>
                    <dd>
                      {item.connectorDisplayName || connection?.display_name || "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>{zh ? "Bot ID" : "Bot ID"}</dt>
                    <dd>{connection?.external_account_id || "—"}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Replica Region" : "Replica region"}</dt>
                    <dd>{item.replicaRegion || (zh ? "未上报" : "Not reported")}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Gateway Ready" : "Gateway ready"}</dt>
                    <dd>{booleanValue(item.gatewayReady, zh)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "部署同步" : "State synchronized"}</dt>
                    <dd>{booleanValue(item.stateSynchronized, zh)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "Connector 看到的 Server" : "Servers visible to Connector"}</dt>
                    <dd>{item.visibleServerCount ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "最后心跳" : "Last heartbeat"}</dt>
                    <dd>{formatTime(connection?.last_seen_at)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "最后 Server 同步" : "Last Server sync"}</dt>
                    <dd>{formatTime(item.catalog?.synced_at)}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "可见 Channel" : "Visible channels"}</dt>
                    <dd>{item.catalog?.channels.length ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Server ID</dt>
                    <dd>{item.profile.guild_id}</dd>
                  </div>
                </dl>
                {item.lastError && (
                  <p className="discord-server-last-error">
                    <strong>{zh ? "Last error：" : "Last error: "}</strong>
                    {item.lastError}
                  </p>
                )}
              </article>
            );
          })}
          {!statusLoading && serverStatuses.length === 0 && (
            <div className="deployment-empty compact-empty">
              <strong>{zh ? "还没有 Discord Server 配置" : "No Discord server profiles"}</strong>
              <p>
                {zh
                  ? "先建立 Server Profile，Connector 同步后这里会显示连接状态。"
                  : "Create a Server Profile. Its connection status appears here after Connector sync."}
              </p>
            </div>
          )}
        </div>
        <small className="discord-server-status-refresh-note">
          {zh ? "状态每 10 秒自动更新。超过 2 分钟未更新会标记为过期。" : "Status refreshes every 10 seconds. Data older than two minutes is marked stale."}
        </small>
      </section>

      <div className="panel-heading-row discord-event-log-heading">
        <div>
          <p className="tape-label">DISCORD EVENT LOG</p>
          <h2>{zh ? "Discord 触发与路由日志" : "Discord trigger and routing logs"}</h2>
          <p>
            {zh
              ? "查看 Tag 是否到达 Gateway、是否命中部署、Runtime 结果与发送状态。不会保存消息正文。"
              : "See whether a Tag reached the Gateway, matched a deployment, reached Runtime, and was delivered. Message text is not stored."}
          </p>
        </div>
        <button className="paper-button" onClick={() => void load()} disabled={loading}>
          {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
        </button>
      </div>

      <div className="discord-event-log-filters">
        <label>
          {zh ? "Server" : "Server"}
          <select
            value={serverProfileId}
            onChange={(event) => changeFilter(setServerProfileId, event.currentTarget.value)}
          >
            <option value="all">{zh ? "全部 Server" : "All servers"}</option>
            {profiles.map((profile) => (
              <option value={profile.id} key={profile.id}>
                {profile.guild_name} · {profile.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {zh ? "等级" : "Level"}
          <select
            value={level}
            onChange={(event) =>
              changeFilter(
                (value) => setLevel(value as "all" | DiscordConnectorLogLevel),
                event.currentTarget.value
              )
            }
          >
            <option value="all">{zh ? "全部" : "All"}</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>
        </label>
        <label>
          {zh ? "事件" : "Event"}
          <select
            value={eventType}
            onChange={(event) => changeFilter(setEventType, event.currentTarget.value)}
          >
            <option value="all">{zh ? "全部事件" : "All events"}</option>
            {EVENT_TYPES.map((value) => (
              <option value={value} key={value}>
                {labelEvent(value, zh)}
              </option>
            ))}
          </select>
        </label>
        <label className="discord-event-log-auto-refresh">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(event) => setAutoRefresh(event.currentTarget.checked)}
          />
          {zh ? "每 5 秒刷新" : "Refresh every 5 seconds"}
        </label>
        <span className="discord-event-log-count">
          {total} {zh ? "条事件" : "events"}
        </span>
      </div>

      {error && <p className="error-note">{error}</p>}

      <div className="discord-event-log-list">
        {!loading && items.length === 0 && (
          <div className="deployment-empty compact-empty">
            <strong>{zh ? "没有符合条件的日志" : "No matching log events"}</strong>
            <p>
              {zh
                ? "先检查上方 Server 连接状态。在 Discord 中直接 Tag Bot 后，这里应出现“收到 Bot Tag”。"
                : "Check Server connection status above first. Mention the Bot in Discord and a “Bot mention received” event should appear."}
            </p>
          </div>
        )}
        {items.map((item) => (
          <article className={`discord-event-log-item log-${item.level}`} key={item.id}>
            <div className="discord-event-log-meta">
              <time dateTime={item.occurred_at}>{formatTime(item.occurred_at)}</time>
              <span className={`discord-event-log-level log-${item.level}`}>{item.level}</span>
              <strong>{labelEvent(item.event_type, zh)}</strong>
            </div>
            <p>{item.message}</p>
            <small>
              {item.guild_name || item.guild_id}
              {item.channel_name && ` · #${item.channel_name}`}
              {item.thread_name && ` · ${item.thread_name}`}
              {item.character_name && ` · ${item.character_name}`}
              {item.source_message_id && ` · Message ${item.source_message_id}`}
            </small>
            {Object.keys(item.details).length > 0 && (
              <details>
                <summary>{zh ? "诊断资料" : "Diagnostic details"}</summary>
                <pre>{JSON.stringify(item.details, null, 2)}</pre>
              </details>
            )}
          </article>
        ))}
      </div>

      <Pagination
        page={page}
        pages={pages}
        total={total}
        disabled={loading}
        onPage={setPage}
      />
    </section>
  );
}
'''
Path("web/src/DiscordEventLogPanel.tsx").write_text(panel_source, encoding="utf-8")

css_path = Path("web/src/discordEventLog.css")
css = css_path.read_text(encoding="utf-8")
css += r'''

.discord-server-status-section {
  display: grid;
  gap: 14px;
  padding-bottom: 20px;
  border-bottom: 1px dashed rgb(69 78 86 / 24%);
}

.discord-server-status-heading p {
  margin: 5px 0 0;
  max-width: 780px;
}

.discord-server-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(330px, 100%), 1fr));
  gap: 12px;
}

.discord-server-status-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgb(69 78 86 / 18%);
  border-left-width: 5px;
  border-radius: 12px;
  background: rgb(255 254 249 / 90%);
}

.discord-server-status-card.server-link-connected {
  border-left-color: #527c62;
}

.discord-server-status-card.server-link-stale,
.discord-server-status-card.server-link-server_not_seen {
  border-left-color: #a77a28;
}

.discord-server-status-card.server-link-connector_error,
.discord-server-status-card.server-link-connector_offline {
  border-left-color: #a34e4e;
}

.discord-server-status-card.is-selected {
  box-shadow: 0 0 0 2px rgb(82 124 134 / 18%);
}

.discord-server-status-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.discord-server-status-title div {
  display: grid;
  gap: 3px;
}

.server-link-badge {
  flex: none;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgb(76 87 96 / 10%);
  font-size: 0.76rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.discord-server-status-card > p {
  margin: 0;
  font-size: 0.9rem;
}

.discord-server-status-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  margin: 0;
}

.discord-server-status-details div {
  min-width: 0;
}

.discord-server-status-details dt {
  color: var(--muted-ink, #65717a);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.discord-server-status-details dd {
  margin: 2px 0 0;
  overflow-wrap: anywhere;
  font-size: 0.86rem;
  font-weight: 600;
}

.discord-server-last-error {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgb(163 78 78 / 9%);
  overflow-wrap: anywhere;
}

.discord-server-status-refresh-note {
  justify-self: end;
}

@media (max-width: 520px) {
  .discord-server-status-title {
    display: grid;
  }

  .server-link-badge {
    justify-self: start;
  }

  .discord-server-status-details {
    grid-template-columns: 1fr;
  }
}
'''
css_path.write_text(css, encoding="utf-8")

test_path = Path("tests/test_discord_connector.py")
test_text = test_path.read_text(encoding="utf-8")
heartbeat_test = r'''


def test_connector_heartbeat_persists_runtime_diagnostics(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "discord-heartbeat-diagnostics.db"))
    client = TestClient(app)
    login(client)
    connection = create_connection(client)

    response = client.post(
        "/api/connectors/discord/heartbeat",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "bot_user_id": "bot-123",
            "bot_display_name": "CharacterRelayBot#0001",
            "status": "connected",
            "last_error": "",
            "replica_region": "asia-southeast1-eqsg3a",
            "gateway_ready": True,
            "state_synchronized": True,
            "visible_server_count": 2,
        },
    )
    assert response.status_code == 204, response.text

    listed = client.get("/api/connections")
    assert listed.status_code == 200, listed.text
    updated = listed.json()[0]
    assert updated["status"] == "connected"
    assert updated["last_seen_at"] is not None
    assert updated["external_account_id"] == "bot-123"
    assert updated["metadata"]["connector_display_name"] == "CharacterRelayBot#0001"
    assert updated["metadata"]["replica_region"] == "asia-southeast1-eqsg3a"
    assert updated["metadata"]["gateway_ready"] is True
    assert updated["metadata"]["state_synchronized"] is True
    assert updated["metadata"]["visible_server_count"] == 2
'''
if "test_connector_heartbeat_persists_runtime_diagnostics" in test_text:
    raise RuntimeError("Heartbeat diagnostics test already exists")
test_path.write_text(test_text + heartbeat_test, encoding="utf-8")
