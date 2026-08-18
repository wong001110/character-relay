import { useEffect, useMemo, useState } from "react";

import {
  discoveryApi,
  type DiscoveryDecision,
  type DiscoveryExposure,
  type DiscoveryMode,
  type DiscoveryProfile,
  type DiscoverySession,
  type DiscoveryShare
} from "./discoveryApi";
import "./deployment-discovery.css";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

const emptyProfile = (deploymentId: string): DiscoveryProfile => ({
  deployment_id: deploymentId,
  mode: "off",
  youtube_enabled: false,
  bilibili_enabled: false,
  bilibili_experimental_available: false,
  auto_share_enabled: false,
  auto_global_enabled: false,
  daily_share_budget: 1,
  share_cooldown_minutes: 180
});

function score(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "—";
}

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

export function DeploymentDiscoveryPanel({ deploymentId, disabled = false, zh }: Props) {
  const [profile, setProfile] = useState<DiscoveryProfile>(() => emptyProfile(deploymentId));
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [exposures, setExposures] = useState<DiscoveryExposure[]>([]);
  const [decisions, setDecisions] = useState<DiscoveryDecision[]>([]);
  const [shares, setShares] = useState<DiscoveryShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<"overview" | "perception" | "decisions" | "shares">("overview");
  const [lastEnabledMode, setLastEnabledMode] = useState<Exclude<DiscoveryMode, "off">>("shadow");

  async function load() {
    try {
      setLoading(true);
      const [nextProfile, nextSessions, nextExposures, nextDecisions, nextShares] =
        await Promise.all([
          discoveryApi.profile(deploymentId),
          discoveryApi.sessions(deploymentId),
          discoveryApi.exposures(deploymentId),
          discoveryApi.decisions(deploymentId),
          discoveryApi.shares(deploymentId)
        ]);
      setProfile(nextProfile);
      if (nextProfile.mode !== "off") setLastEnabledMode(nextProfile.mode);
      setSessions(nextSessions.items);
      setExposures(nextExposures.items);
      setDecisions(nextDecisions.items);
      setShares(nextShares.items);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setProfile(emptyProfile(deploymentId));
    void load();
  }, [deploymentId]);

  const enabled = profile.mode !== "off";
  const latest = sessions[0];
  const pendingShares = useMemo(
    () => shares.filter((item) => item.status === "pending_review"),
    [shares]
  );

  async function save(next: DiscoveryProfile) {
    const previous = profile;
    setProfile(next);
    try {
      setSaving(true);
      setError("");
      const saved = await discoveryApi.updateProfile(deploymentId, next);
      setProfile(saved);
      if (saved.mode !== "off") setLastEnabledMode(saved.mode);
    } catch (reason) {
      setProfile(previous);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  function toggleEnabled() {
    const mode: DiscoveryMode = enabled ? "off" : lastEnabledMode;
    void save({ ...profile, mode });
  }

  function setMode(mode: Exclude<DiscoveryMode, "off">) {
    setLastEnabledMode(mode);
    void save({ ...profile, mode });
  }

  async function browse() {
    const platform = profile.youtube_enabled
      ? "youtube"
      : profile.bilibili_enabled
        ? "bilibili"
        : undefined;
    if (!platform) return;
    try {
      setSaving(true);
      setError("");
      await discoveryApi.browse(deploymentId, platform);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function resolveShare(item: DiscoveryShare, action: "approve" | "reject") {
    try {
      setSaving(true);
      if (action === "approve") await discoveryApi.approve(deploymentId, item.id);
      else await discoveryApi.reject(deploymentId, item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="deployment-form-wide discovery-sheet">
      <div className="deployment-form-divider discovery-heading">
        <div>
          <strong>{zh ? "角色探索 / Discovery" : "Character Discovery"}</strong>
          <span>
            {zh
              ? "决定这个 Deployment 能否在空闲时浏览外部内容，以及可以去哪些平台。默认关闭。"
              : "Control whether this Deployment may browse external content during leisure time and which sources it may visit. Default is off."}
          </span>
        </div>
        <label className="discovery-master-toggle">
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled || saving || loading}
            onChange={toggleEnabled}
          />
          <strong>{enabled ? "ON" : "OFF"}</strong>
        </label>
      </div>

      {error && <small className="deployment-inline-error">{error}</small>}

      <div className={`discovery-controls${enabled ? "" : " is-disabled"}`}>
        <fieldset disabled={!enabled || disabled || saving}>
          <legend>{zh ? "可以去哪里" : "Allowed sources"}</legend>
          <label>
            <input
              type="checkbox"
              checked={profile.youtube_enabled}
              onChange={() => void save({ ...profile, youtube_enabled: !profile.youtube_enabled })}
            />
            <span>YouTube</span>
          </label>
          <label title={!profile.bilibili_experimental_available ? "Experimental source disabled globally" : ""}>
            <input
              type="checkbox"
              checked={profile.bilibili_enabled}
              disabled={!profile.bilibili_experimental_available || !enabled || disabled || saving}
              onChange={() => void save({ ...profile, bilibili_enabled: !profile.bilibili_enabled })}
            />
            <span>Bilibili <em>EXPERIMENTAL</em></span>
          </label>
          {!profile.bilibili_experimental_available && (
            <small>{zh ? "Bilibili 目前被系统级 Experimental 开关禁用。" : "Bilibili is disabled by the system Experimental gate."}</small>
          )}
        </fieldset>

        <fieldset disabled={!enabled || disabled || saving}>
          <legend>{zh ? "分享行为" : "Sharing behavior"}</legend>
          {(["shadow", "review", "auto"] as const).map((mode) => (
            <label key={mode}>
              <input
                type="radio"
                name={`discovery-mode-${deploymentId}`}
                checked={profile.mode === mode}
                onChange={() => setMode(mode)}
              />
              <span>{mode.toUpperCase()}</span>
            </label>
          ))}
          {profile.mode === "auto" && (
            <label>
              <input
                type="checkbox"
                checked={profile.auto_share_enabled}
                onChange={() => void save({ ...profile, auto_share_enabled: !profile.auto_share_enabled })}
              />
              <span>{zh ? "允许此 Deployment AUTO 分享" : "Allow AUTO for this Deployment"}</span>
              {!profile.auto_global_enabled && <small>{zh ? "全局 AUTO 仍关闭" : "Global AUTO remains disabled"}</small>}
            </label>
          )}
        </fieldset>

        <fieldset disabled={!enabled || disabled || saving}>
          <legend>{zh ? "分享限制" : "Share limits"}</legend>
          <label>
            <span>{zh ? "每日预算" : "Daily budget"}</span>
            <input
              type="number"
              min={0}
              max={8}
              value={profile.daily_share_budget}
              onChange={(event) => setProfile({ ...profile, daily_share_budget: Number(event.currentTarget.value) })}
              onBlur={() => void save(profile)}
            />
          </label>
          <label>
            <span>{zh ? "冷却（分钟）" : "Cooldown (minutes)"}</span>
            <input
              type="number"
              min={15}
              max={1440}
              value={profile.share_cooldown_minutes}
              onChange={(event) => setProfile({ ...profile, share_cooldown_minutes: Number(event.currentTarget.value) })}
              onBlur={() => void save(profile)}
            />
          </label>
        </fieldset>
      </div>

      <div className="discovery-observatory-heading">
        <div>
          <span className="tape-label">DISCOVERY OBSERVATORY</span>
          <strong>{zh ? "这个角色最近在外部世界看到了什么" : "What this Character has encountered outside Discord"}</strong>
        </div>
        <div>
          <button className="paper-button" type="button" onClick={() => void load()} disabled={loading || saving}>
            {zh ? "刷新" : "Refresh"}
          </button>
          <button
            className="paper-button"
            type="button"
            onClick={() => void browse()}
            disabled={!enabled || saving || (!profile.youtube_enabled && !profile.bilibili_enabled)}
          >
            {zh ? "手动浏览" : "Run browse"}
          </button>
        </div>
      </div>

      <nav className="discovery-subtabs" aria-label="Discovery observatory sections">
        {(["overview", "perception", "decisions", "shares"] as const).map((item) => (
          <button
            key={item}
            type="button"
            className={view === item ? "is-active" : ""}
            onClick={() => setView(item)}
          >
            {item}
            {item === "shares" && pendingShares.length > 0 ? ` (${pendingShares.length})` : ""}
          </button>
        ))}
      </nav>

      {view === "overview" && (
        <div className="discovery-overview">
          <div className="discovery-metrics">
            <article><span>{zh ? "状态" : "State"}</span><strong>{profile.mode.toUpperCase()}</strong></article>
            <article><span>{zh ? "候选" : "Candidates"}</span><strong>{latest?.candidate_count ?? 0}</strong></article>
            <article><span>NOTICE</span><strong>{latest?.notice_count ?? 0}</strong></article>
            <article><span>OPEN</span><strong>{latest?.open_count ?? 0}</strong></article>
            <article><span>WATCH</span><strong>{latest?.watch_count ?? 0}</strong></article>
            <article><span>ENGAGE</span><strong>{latest?.engage_count ?? 0}</strong></article>
          </div>
          <div className="discovery-list">
            {sessions.slice(0, 8).map((item) => (
              <article key={item.id}>
                <strong>{item.platform || item.source || "Discovery"} · {item.status}</strong>
                <span>{stamp(item.started_at ?? item.scheduled_start_at, zh)}</span>
                <small>{item.candidate_count} → {item.notice_count} → {item.open_count} → {item.watch_count} → {item.engage_count}</small>
                {item.error && <small className="deployment-inline-error">{item.error}</small>}
              </article>
            ))}
            {!loading && sessions.length === 0 && <small>{zh ? "还没有浏览记录。" : "No browsing sessions yet."}</small>}
          </div>
        </div>
      )}

      {view === "perception" && (
        <div className="discovery-card-grid">
          {exposures.map((item) => (
            <article key={item.id}>
              {item.item.thumbnail_url && <img src={item.item.thumbnail_url} alt="" />}
              <div>
                <span>{item.attention_level.toUpperCase()} · {score(item.interest_score)}</span>
                <strong>{item.item.title || item.item.canonical_key}</strong>
                <small>{item.item.source} · {item.item.creator}</small>
                <p>{item.subjective_reason || (zh ? "没有记录主观理由" : "No subjective reason recorded")}</p>
              </div>
            </article>
          ))}
          {!loading && exposures.length === 0 && <small>{zh ? "角色还没有实际注意到任何 Discovery 内容。" : "The Character has no recorded Discovery exposures yet."}</small>}
        </div>
      )}

      {view === "decisions" && (
        <div className="discovery-list">
          {decisions.map((item) => (
            <article key={item.id}>
              <strong>{item.decision} · {item.motivation || "—"}</strong>
              <span>{score(item.confidence)} · {stamp(item.created_at, zh)}</span>
              <small>{item.item.title || item.item.canonical_key}</small>
              <details>
                <summary>{zh ? "证据" : "Evidence"}</summary>
                <pre>{JSON.stringify({ scores: item.scores, evidence: item.evidence }, null, 2)}</pre>
              </details>
            </article>
          ))}
        </div>
      )}

      {view === "shares" && (
        <div className="discovery-list">
          {shares.map((item) => (
            <article key={item.id}>
              <strong>{item.status} · {item.motivation || item.mode}</strong>
              <span>{score(item.confidence)} · {stamp(item.created_at, zh)}</span>
              <small>{item.item.title || item.item.canonical_key}</small>
              {item.draft_text && <p>{item.draft_text}</p>}
              {item.last_error && <small className="deployment-inline-error">{item.last_error}</small>}
              {item.status === "pending_review" && (
                <div className="discovery-share-actions">
                  <button type="button" className="ink-button" disabled={saving} onClick={() => void resolveShare(item, "approve")}>
                    {zh ? "批准" : "Approve"}
                  </button>
                  <button type="button" className="paper-button" disabled={saving} onClick={() => void resolveShare(item, "reject")}>
                    {zh ? "拒绝" : "Reject"}
                  </button>
                </div>
              )}
            </article>
          ))}
          {!loading && shares.length === 0 && <small>{zh ? "暂无分享记录。" : "No share records yet."}</small>}
        </div>
      )}
    </section>
  );
}
