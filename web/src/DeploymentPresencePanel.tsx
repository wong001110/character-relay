import { useCallback, useEffect, useMemo, useState } from "react";

import { CharacterPortrait } from "./CharacterPortrait";
import {
  deploymentApi,
  type CharacterDeployment
} from "./deploymentApi";
import {
  deploymentPresenceApi,
  type DeploymentPresenceRhythmView,
  type DeploymentPresenceState,
  type DeploymentPresenceView
} from "./deploymentPresenceApi";
import { pageCount, pageItems } from "./conversationPagination";
import { Pagination } from "./Pagination";
import "./deployment-presence.css";

interface Props {
  serverProfileId: string;
  zh: boolean;
}

interface PresenceRow {
  deployment: CharacterDeployment;
  presence: DeploymentPresenceView | null;
  rhythm: DeploymentPresenceRhythmView | null;
  error: string;
  rhythmError: string;
}

const REFRESH_INTERVAL_MS = 15_000;
const PRESENCE_PAGE_SIZE = 8;

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function rhythmStamp(value: string | null, timezone: string, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  try {
    return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
      dateStyle: "medium",
      timeStyle: "short",
      ...(timezone ? { timeZone: timezone } : {})
    }).format(parsed);
  } catch {
    return stamp(value, zh);
  }
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
  if (normalized === "rhythm") return zh ? "日常作息" : "Daily rhythm";
  return normalized;
}

function nextStateLabel(value: string, zh: boolean): string {
  if (value === "sleeping") return zh ? "入睡" : "Sleep";
  if (value === "idle") return zh ? "醒来" : "Wake";
  return value || "—";
}

export function DeploymentPresencePanel({ serverProfileId, zh }: Props) {
  const [rows, setRows] = useState<PresenceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async (quiet = false) => {
    try {
      if (quiet) setRefreshing(true);
      else setLoading(true);
      setError("");
      const deployments = await deploymentApi.listDeploymentsForServer(serverProfileId);
      const [presenceResults, rhythmResults] = await Promise.all([
        Promise.allSettled(
          deployments.map((deployment) => deploymentPresenceApi.get(deployment.id))
        ),
        Promise.allSettled(
          deployments.map((deployment) => deploymentPresenceApi.getRhythm(deployment.id))
        )
      ]);
      setRows(
        deployments.map((deployment, index) => {
          const presenceResult = presenceResults[index];
          const rhythmResult = rhythmResults[index];
          return {
            deployment,
            presence: presenceResult.status === "fulfilled" ? presenceResult.value : null,
            rhythm: rhythmResult.status === "fulfilled" ? rhythmResult.value : null,
            error:
              presenceResult.status === "rejected"
                ? presenceResult.reason instanceof Error
                  ? presenceResult.reason.message
                  : String(presenceResult.reason)
                : "",
            rhythmError:
              rhythmResult.status === "rejected"
                ? rhythmResult.reason instanceof Error
                  ? rhythmResult.reason.message
                  : String(rhythmResult.reason)
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
  const pages = pageCount(rows.length, PRESENCE_PAGE_SIZE);
  const visibleRows = useMemo(
    () => pageItems(rows, page, PRESENCE_PAGE_SIZE),
    [rows, page]
  );

  useEffect(() => {
    setPage(1);
  }, [serverProfileId]);

  useEffect(() => {
    setPage((current) => Math.min(Math.max(1, current), pages));
  }, [pages]);

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
              ? "这里显示每个 Deployment 的实时生活状态与下一次作息变化。Discovery 开始浏览时会自动切换为 Browsing；睡眠期间角色 Runtime 与 Discovery 会暂停。"
              : "Live Deployment-scoped state plus the next daily-rhythm transition. Discovery switches Presence to Browsing during a session; sleeping pauses character runtime and Discovery."}
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
        {visibleRows.map(({ deployment, presence, rhythm, error: rowError, rhythmError }) => {
          const currentState = presence?.state ?? "idle";
          const timezone = rhythm?.schedule_timezone ?? "";
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

                  <div className={`presence-rhythm-strip${rhythm?.enabled ? " is-enabled" : ""}`}>
                    <div>
                      <span>☾ {zh ? "下次入睡" : "Next sleep"}</span>
                      <strong>
                        {rhythm?.enabled
                          ? rhythmStamp(rhythm.scheduled_sleep_at, timezone, zh)
                          : zh
                            ? "作息未启用"
                            : "Rhythm off"}
                      </strong>
                    </div>
                    <div>
                      <span>☀ {zh ? "下次醒来" : "Next wake"}</span>
                      <strong>
                        {rhythm?.enabled
                          ? rhythmStamp(rhythm.scheduled_wake_at, timezone, zh)
                          : "—"}
                      </strong>
                    </div>
                    <div>
                      <span>→ {zh ? "下一次变化" : "Next transition"}</span>
                      <strong>
                        {rhythm?.enabled && rhythm.next_transition_at
                          ? `${nextStateLabel(rhythm.next_state, zh)} · ${rhythmStamp(rhythm.next_transition_at, timezone, zh)}`
                          : "—"}
                      </strong>
                    </div>
                    {rhythm?.enabled && timezone && <small>{timezone}</small>}
                  </div>

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
                      <div>
                        <dt>{zh ? "作息状态" : "Daily rhythm"}</dt>
                        <dd>{rhythm?.enabled ? "enabled" : rhythmError ? "unavailable" : "off"}</dd>
                      </div>
                      <div>
                        <dt>{zh ? "作息读取" : "Rhythm read"}</dt>
                        <dd>{rhythmError || "ok"}</dd>
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

      <Pagination page={page} pages={pages} total={rows.length} onPage={setPage} />

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
