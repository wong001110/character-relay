import { useCallback, useEffect, useState } from "react";

import {
  deploymentApi,
  type CharacterDeployment,
  type DeploymentLog,
  type DeploymentLogLevel
} from "./deploymentApi";

interface Props {
  deployment: CharacterDeployment;
  zh: boolean;
  onClose: () => void;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function eventLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function DeploymentLogsPanel({ deployment, zh, onClose }: Props) {
  const [logs, setLogs] = useState<DeploymentLog[]>([]);
  const [level, setLevel] = useState<"all" | DeploymentLogLevel>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    try {
      const next = await deploymentApi.listDeploymentLogs({
        connectionId: deployment.connection_id,
        deploymentId: deployment.id,
        level,
        limit: 200
      });
      setLogs(next);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [deployment.connection_id, deployment.id, level]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void load(), 5_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load]);

  return (
    <div className="deployment-log-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="paper-sheet deployment-log-panel"
        role="dialog"
        aria-modal="true"
        aria-label={zh ? "部署诊断日志" : "Deployment diagnostic logs"}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="panel-heading-row deployment-log-heading">
          <div>
            <p className="tape-label">CONNECTOR LOGS</p>
            <h2>{deployment.character_display_name}</h2>
            <p>
              {deployment.workspace_name} · {deployment.server_profile_name || deployment.channel_name}
            </p>
          </div>
          <button className="paper-button" onClick={onClose}>
            {zh ? "关闭" : "Close"}
          </button>
        </div>

        <div className="deployment-log-controls">
          <label>
            {zh ? "等级" : "Level"}
            <select
              value={level}
              onChange={(event) =>
                setLevel(event.currentTarget.value as "all" | DeploymentLogLevel)
              }
            >
              <option value="all">{zh ? "全部" : "All"}</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="debug">Debug</option>
            </select>
          </label>
          <label className="deployment-log-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.currentTarget.checked)}
            />
            {zh ? "每 5 秒刷新" : "Refresh every 5 seconds"}
          </label>
          <button className="paper-button" onClick={() => void load()} disabled={loading}>
            {loading ? (zh ? "读取中…" : "Loading…") : zh ? "立即刷新" : "Refresh now"}
          </button>
        </div>

        <p className="deployment-log-privacy-note">
          {zh
            ? "日志只保存路由、状态、延迟与错误等诊断资料，不保存 Discord 消息正文。"
            : "Logs store routing, status, latency, and error diagnostics. Discord message text is not stored."}
        </p>

        {error && <p className="error-note">{error}</p>}

        <div className="deployment-log-list">
          {!loading && logs.length === 0 && (
            <div className="deployment-empty compact-empty">
              <strong>{zh ? "目前没有诊断事件" : "No diagnostic events yet"}</strong>
              <p>
                {zh
                  ? "先在 Discord 中 @ Bot 或回复角色消息，再观察是否出现 runtime message received。"
                  : "Mention the bot or reply to a character message, then look for runtime message received."}
              </p>
            </div>
          )}
          {logs.map((item) => (
            <article className={`deployment-log-item log-${item.level}`} key={item.id}>
              <div className="deployment-log-meta">
                <time dateTime={item.created_at}>{formatTime(item.created_at)}</time>
                <span className={`deployment-log-level log-${item.level}`}>{item.level}</span>
                <strong>{eventLabel(item.event_type)}</strong>
              </div>
              <p>{item.message}</p>
              {(item.workspace_id || item.channel_id || item.source_message_id) && (
                <small>
                  {item.workspace_id && `Server ${item.workspace_id}`}
                  {item.channel_id && ` · Channel ${item.channel_id}`}
                  {item.thread_id && ` · Thread ${item.thread_id}`}
                  {item.source_message_id && ` · Message ${item.source_message_id}`}
                </small>
              )}
              {Object.keys(item.details).length > 0 && (
                <details>
                  <summary>{zh ? "查看资料" : "View details"}</summary>
                  <pre>{JSON.stringify(item.details, null, 2)}</pre>
                </details>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
