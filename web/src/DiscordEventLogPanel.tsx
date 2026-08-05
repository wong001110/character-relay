import { useCallback, useEffect, useMemo, useState } from "react";

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
  "message_received",
  "mention_received",
  "reply_received",
  "ignored_no_deployment",
  "audience_ambiguous",
  "audience_not_found",
  "ignored_participation_mode",
  "runtime_started",
  "runtime_silent",
  "expression_candidates",
  "expression_execution_success",
  "expression_skipped",
  "expression_execution_error",
  "delivery_success",
  "delivery_error",
  "handler_error"
] as const;

const SHOW_SERVER_CONNECTION_STATUS = false;

const EVENT_LABELS: Record<string, { en: string; zh: string }> = {
  message_received: { en: "Gateway message received", zh: "Gateway 收到消息" },
  mention_received: { en: "Bot mention received", zh: "收到 Bot Tag" },
  reply_received: { en: "Character reply received", zh: "收到角色回复触发" },
  ignored_no_deployment: { en: "No matching deployment", zh: "没有命中部署" },
  audience_ambiguous: { en: "Character selection required", zh: "角色选择不明确" },
  audience_not_found: { en: "Character not found", zh: "没有找到指定角色" },
  ignored_participation_mode: { en: "Blocked by participation mode", zh: "参与模式未允许" },
  runtime_started: { en: "Runtime request started", zh: "开始调用角色 Runtime" },
  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },
  expression_candidates: { en: "Expression candidates retrieved", zh: "已检索表达候选" },
  expression_execution_success: { en: "Expression applied", zh: "表达执行成功" },
  expression_skipped: { en: "Expression skipped", zh: "未使用 Server 表达" },
  expression_execution_error: { en: "Expression failed", zh: "表达执行失败" },
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
    if (!SHOW_SERVER_CONNECTION_STATUS) return;
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
      {SHOW_SERVER_CONNECTION_STATUS && (
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
                    <dt>{zh ? "Replica ID" : "Replica ID"}</dt>
                    <dd>{item.replicaId || (zh ? "未上报" : "Not reported")}</dd>
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
      )}

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
