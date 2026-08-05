import { useCallback, useEffect, useState } from "react";

import {
  deploymentApi,
  type DiscordConnectorLog,
  type DiscordConnectorLogLevel,
  type DiscordServerProfile
} from "./deploymentApi";
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

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function labelEvent(value: string, zh: boolean): string {
  const label = EVENT_LABELS[value];
  return label ? (zh ? label.zh : label.en) : value.replaceAll("_", " ");
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

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

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
                ? "在 Discord 中直接 Tag Bot 后，这里应先出现“收到 Bot Tag”，即使没有命中任何角色。"
                : "Mention the Bot in Discord. A “Bot mention received” event should appear even when no character deployment matches."}
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
