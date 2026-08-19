import { useCallback, useEffect, useMemo, useState } from "react";

import { CharacterPortrait } from "./CharacterPortrait";
import {
  deploymentApi,
  type CharacterDeployment
} from "./deploymentApi";
import {
  deploymentPresenceApi,
  type DeploymentPresenceState,
  type DeploymentPresenceView
} from "./deploymentPresenceApi";
import "./deployment-presence.css";

interface Props {
  serverProfileId: string;
  zh: boolean;
}

interface PresenceRow {
  deployment: CharacterDeployment;
  presence: DeploymentPresenceView | null;
  error: string;
}

const REFRESH_INTERVAL_MS = 15_000;

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function stateLabel(state: DeploymentPresenceState, activityType: string, zh: boolean): string {
  const activity = activityType.trim();
  if (state === "browsing") {
    const source = activity ? activity[0].toUpperCase() + activity.slice(1) : zh ? "外部内容" : "External content";
    return zh ? `浏览中 · ${source}` : `Browsing · ${source}`;
  }
  if (state === "sleeping") return zh ? "睡眠中" : "Sleeping";
  if (state === "busy") return zh ? "忙碌中" : "Busy";
  return zh ? "空闲" : "Idle";
}

function stateIcon(state: DeploymentPresenceState): string {
  if (state === "browsing") return "◐";
  if (state === "sleeping") return "☾";
  if (state === "busy") return "●";
  return "○";
}

function sourceLabel(source: string, zh: boolean): string {
  const normalized = source.replaceAll("_", " ").trim();
  if (!normalized || normalized === "default") return zh ? "默认状态" : "Default state";
  if (normalized === "discovery activity") return zh ? "Discovery 活动" : "Discovery activity";
  return normalized;
}

export function DeploymentPresencePanel({ serverProfileId, zh }: Props) {
  const [rows, setRows] = useState<PresenceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    try {
      if (quiet) setRefreshing(true);
      else setLoading(true);
      setError("");
      const deployments = await deploymentApi.listDeploymentsForServer(serverProfileId);
      const results = await Promise.allSettled(
        deployments.map((deployment) => deploymentPresenceApi.get(deployment.id))
      );
      setRows(
        deployments.map((deployment, index) => {
          const result = results[index];
          return {
            deployment,
            presence: result.status === "fulfilled" ? result.value : null,
            error:
              result.status === "rejected"
                ? result.reason instanceof Error
                  ? result.reason.message
                  : String(result.reason)
                : ""
          };
        })
      );
      setLastRefreshedAt(new Date().toISOString());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [serverProfileId]);

  useEffect(() => {
    void load(false);
    const timer = window.setInterval(() => void load(true), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const counts = useMemo(() => {
    const next: Record<DeploymentPresenceState, number> = {
      idle: 0,
      browsing: 0,
      sleeping: 0,
      busy: 0
    };
    for (const row of rows) {
      if (row.presence) next[row.presence.state] += 1;
    }
    return next;
  }, [rows]);

  if (loading) {
    return (
      <section className="paper-sheet presence-observatory-empty">
        {zh ? "正在读取 Character Presence…" : "Loading Character Presence…"}
      </section>
    );
  }

  return (
    <section className="presence-observatory-shell">
      <header className="paper-sheet presence-observatory-header">
        <div>
          <span className="tape-label">LIVE PRESENCE</span>
          <h2>{zh ? "角色当前状态" : "Current Character Presence"}</h2>
          <p>
            {zh
              ? "这里显示每个 Deployment 的实时生活状态。Discovery 开始浏览时会自动切换为 Browsing，结束后恢复 Idle。"
              : "Live Deployment-scoped state. Discovery automatically switches Presence to Browsing during a session and restores Idle afterward."}
          </p>
        </div>
        <div className="presence-observatory-refresh">
          <small>
            {zh ? "每 15 秒自动刷新" : "Auto-refresh every 15s"}
            {lastRefreshedAt ? ` · ${stamp(lastRefreshedAt, zh)}` : ""}
          </small>
          <button
            type="button"
            className="paper-button"
            disabled={refreshing}
            onClick={() => void load(true)}
          >
            {refreshing ? (zh ? "刷新中…" : "Refreshing…") : zh ? "刷新" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <p className="error-note">{error}</p>}

      <div className="presence-observatory-metrics" aria-label={zh ? "Presence 概览" : "Presence overview"}>
        <article className="paper-sheet presence-metric presence-idle">
          <span>○ {zh ? "空闲" : "Idle"}</span>
          <strong>{counts.idle}</strong>
        </article>
        <article className="paper-sheet presence-metric presence-browsing">
          <span>◐ {zh ? "浏览中" : "Browsing"}</span>
          <strong>{counts.browsing}</strong>
        </article>
        <article className="paper-sheet presence-metric presence-sleeping">
          <span>☾ {zh ? "睡眠中" : "Sleeping"}</span>
          <strong>{counts.sleeping}</strong>
        </article>
        <article className="paper-sheet presence-metric presence-busy">
          <span>● {zh ? "忙碌中" : "Busy"}</span>
          <strong>{counts.busy}</strong>
        </article>
      </div>

      <div className="presence-card-grid">
        {rows.map(({ deployment, presence, error: rowError }) => {
          const currentState = presence?.state ?? "idle";
          return (
            <article
              key={deployment.id}
              className={`paper-sheet presence-card presence-card-${currentState}${deployment.status === "active" ? "" : " is-inactive-deployment"}`}
            >
              <header className="presence-card-header">
                <div className="presence-card-character">
                  <span className="presence-card-avatar">
                    <CharacterPortrait
                      cardId={deployment.character_card_id}
                      alt={deployment.character_display_name}
                    />
                  </span>
                  <div>
                    <strong>{deployment.character_display_name}</strong>
                    <small>
                      {deployment.status === "active"
                        ? zh
                          ? "Deployment 运行中"
                          : "Deployment active"
                        : zh
                          ? `Deployment ${deployment.status}`
                          : `Deployment ${deployment.status}`}
                    </small>
                  </div>
                </div>
                {presence ? (
                  <span className={`presence-state-badge state-${presence.state}`}>
                    <span aria-hidden="true">{stateIcon(presence.state)}</span>
                    {stateLabel(presence.state, presence.activity_type, zh)}
                  </span>
                ) : (
                  <span className="presence-state-badge state-unknown">?</span>
                )}
              </header>

              {presence ? (
                <>
                  <dl className="presence-card-facts">
                    <div>
                      <dt>{zh ? "开始" : "Since"}</dt>
                      <dd>{stamp(presence.started_at, zh)}</dd>
                    </div>
                    <div>
                      <dt>
                        {presence.state === "sleeping"
                          ? zh
                            ? "预计醒来"
                            : "Expected wake"
                          : zh
                            ? "预计结束"
                            : "Expected end"}
                      </dt>
                      <dd>{stamp(presence.expected_end_at, zh)}</dd>
                    </div>
                    <div>
                      <dt>{zh ? "来源" : "Source"}</dt>
                      <dd>{sourceLabel(presence.source, zh)}</dd>
                    </div>
                    <div>
                      <dt>{zh ? "角色 Runtime" : "Character runtime"}</dt>
                      <dd>{presence.available_for_character_runtime ? (zh ? "可用" : "Available") : zh ? "暂停" : "Unavailable"}</dd>
                    </div>
                  </dl>
                  <details className="presence-card-details">
                    <summary>{zh ? "运行证据" : "Runtime evidence"}</summary>
                    <dl>
                      <div>
                        <dt>activity_type</dt>
                        <dd>{presence.activity_type || "—"}</dd>
                      </div>
                      <div>
                        <dt>reason</dt>
                        <dd>{presence.reason || "—"}</dd>
                      </div>
                      <div>
                        <dt>{zh ? "Discovery 允许" : "Discovery allowed"}</dt>
                        <dd>{presence.discovery_allowed ? "yes" : "no"}</dd>
                      </div>
                      <div>
                        <dt>{zh ? "持久化" : "Persisted"}</dt>
                        <dd>{presence.persisted ? "yes" : "default fallback"}</dd>
                      </div>
                    </dl>
                  </details>
                </>
              ) : (
                <p className="deployment-inline-error">
                  {rowError || (zh ? "无法读取 Presence。" : "Presence unavailable.")}
                </p>
              )}
            </article>
          );
        })}
      </div>

      {rows.length === 0 && (
        <section className="paper-sheet presence-observatory-empty">
          <strong>{zh ? "这个 Server 还没有 Character Deployment" : "No Character Deployment in this Server yet"}</strong>
          <p>
            {zh
              ? "建立 Deployment 后，这里会显示 Idle、Browsing、Sleeping 与 Busy 等实时状态。"
              : "Add a Deployment to observe Idle, Browsing, Sleeping, and Busy live states here."}
          </p>
        </section>
      )}
    </section>
  );
}
