import { useEffect, useMemo, useState } from "react";

import type { CharacterDeployment } from "./deploymentApi";
import {
  discoveryApi,
  type DiscoveryDecision,
  type DiscoveryExposure,
  type DiscoveryProfile,
  type DiscoverySession,
  type DiscoveryShare
} from "./discoveryApi";

interface Props {
  deployments: CharacterDeployment[];
  zh: boolean;
}

type DiscoveryView = "overview" | "perception" | "decisions" | "shares";

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

export function DiscoveryIntelligencePanel({ deployments, zh }: Props) {
  const [deploymentId, setDeploymentId] = useState(
    deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
  );
  const [profile, setProfile] = useState<DiscoveryProfile | null>(null);
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [exposures, setExposures] = useState<DiscoveryExposure[]>([]);
  const [decisions, setDecisions] = useState<DiscoveryDecision[]>([]);
  const [shares, setShares] = useState<DiscoveryShare[]>([]);
  const [view, setView] = useState<DiscoveryView>("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedDeployment = deployments.find((item) => item.id === deploymentId) ?? null;
  const pendingShares = useMemo(
    () => shares.filter((item) => item.status === "pending_review"),
    [shares]
  );
  const latest = sessions[0];

  useEffect(() => {
    if (!deployments.some((item) => item.id === deploymentId)) {
      setDeploymentId(
        deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
      );
    }
  }, [deploymentId, deployments]);

  async function load() {
    if (!deploymentId) return;
    try {
      setLoading(true);
      setError("");
      const [nextProfile, nextSessions, nextExposures, nextDecisions, nextShares] = await Promise.all([
        discoveryApi.profile(deploymentId),
        discoveryApi.sessions(deploymentId),
        discoveryApi.exposures(deploymentId),
        discoveryApi.decisions(deploymentId),
        discoveryApi.shares(deploymentId)
      ]);
      setProfile(nextProfile);
      setSessions(nextSessions.items);
      setExposures(nextExposures.items);
      setDecisions(nextDecisions.items);
      setShares(nextShares.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [deploymentId]);

  async function browse() {
    if (!profile || profile.mode === "off") return;
    const platform = profile.youtube_enabled
      ? "youtube"
      : profile.bilibili_enabled
        ? "bilibili"
        : undefined;
    if (!platform) return;
    try {
      setLoading(true);
      setError("");
      await discoveryApi.browse(deploymentId, platform);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  async function resolveShare(item: DiscoveryShare, action: "approve" | "reject") {
    try {
      setLoading(true);
      setError("");
      if (action === "approve") await discoveryApi.approve(deploymentId, item.id);
      else await discoveryApi.reject(deploymentId, item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="paper-sheet discovery-intelligence-panel">
      <header className="intelligence-product-heading">
        <div>
          <span className="tape-label">DISCOVERY OBSERVATORY</span>
          <h2>{zh ? "角色最近在外部世界看到了什么" : "What this Character encountered outside Discord"}</h2>
          <p>
            {zh
              ? "这里仅观察与审核运行证据。Discovery ON/OFF、来源和分享预算请在 Deployment Edit 修改。"
              : "This surface observes and reviews runtime evidence only. Change Discovery ON/OFF, sources, and sharing limits in Deployment Edit."}
          </p>
        </div>
        <div className="intelligence-heading-actions">
          <button type="button" className="paper-button" disabled={loading} onClick={() => void load()}>{zh ? "刷新" : "Refresh"}</button>
          <button
            type="button"
            className="paper-button"
            disabled={
              loading ||
              !profile ||
              profile.mode === "off" ||
              (!profile.youtube_enabled && !profile.bilibili_enabled)
            }
            onClick={() => void browse()}
          >
            {zh ? "手动浏览" : "Run browse"}
          </button>
        </div>
      </header>

      <div className="discovery-intelligence-selector">
        <label>
          <span>{zh ? "Deployment" : "Deployment"}</span>
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.currentTarget.value)}>
            {deployments.map((item) => <option key={item.id} value={item.id}>{item.character_display_name} · {item.status}</option>)}
          </select>
        </label>
        <small>{selectedDeployment?.character_display_name ?? "—"}</small>
      </div>

      {error && <small className="deployment-inline-error">{error}</small>}
      {!deploymentId ? (
        <p>{zh ? "这个 Server 还没有 Character Deployment。" : "No Character Deployment exists in this Server."}</p>
      ) : !profile ? (
        <p>{loading ? (zh ? "读取 Discovery evidence…" : "Loading Discovery evidence…") : "—"}</p>
      ) : (
        <>
          <div className="discovery-intelligence-policy-strip">
            <span><small>{zh ? "运行模式" : "Runtime mode"}</small><strong>{profile.mode.toUpperCase()}</strong></span>
            <span><small>{zh ? "来源" : "Sources"}</small><strong>{[profile.youtube_enabled && "YouTube", profile.bilibili_enabled && "Bilibili"].filter(Boolean).join(" · ") || "—"}</strong></span>
            <span><small>{zh ? "待审核分享" : "Pending review"}</small><strong>{pendingShares.length}</strong></span>
          </div>

          <nav className="intelligence-product-subtabs">
            {(["overview", "perception", "decisions", "shares"] as DiscoveryView[]).map((item) => (
              <button type="button" key={item} className={view === item ? "is-active" : ""} onClick={() => setView(item)}>
                {item}{item === "shares" && pendingShares.length ? ` (${pendingShares.length})` : ""}
              </button>
            ))}
          </nav>

          {view === "overview" && (
            <>
              <div className="discovery-metrics">
                <article><span>{zh ? "状态" : "State"}</span><strong>{latest?.status?.toUpperCase() ?? profile.mode.toUpperCase()}</strong></article>
                <article><span>{zh ? "候选" : "Candidates"}</span><strong>{latest?.candidate_count ?? 0}</strong></article>
                <article><span>NOTICE</span><strong>{latest?.notice_count ?? 0}</strong></article>
                <article><span>OPEN</span><strong>{latest?.open_count ?? 0}</strong></article>
                <article><span>WATCH</span><strong>{latest?.watch_count ?? 0}</strong></article>
                <article><span>ENGAGE</span><strong>{latest?.engage_count ?? 0}</strong></article>
              </div>
              <div className="discovery-intelligence-list">
                {sessions.map((item) => (
                  <article key={item.id}>
                    <header><strong>{item.platform || item.source || "Discovery"}</strong><span>{item.status.toUpperCase()}</span></header>
                    <p>{item.reason || item.error || (zh ? "没有额外说明" : "No additional note")}</p>
                    <small>{stamp(item.started_at ?? item.scheduled_start_at, zh)} · {item.planned_duration_minutes} min</small>
                  </article>
                ))}
                {sessions.length === 0 && <small>{zh ? "还没有 browsing session。" : "No browsing sessions yet."}</small>}
              </div>
            </>
          )}

          {view === "perception" && (
            <div className="discovery-intelligence-list">
              {exposures.map((item) => (
                <article key={item.id}>
                  <header><strong>{item.item.title || item.item.url}</strong><span>{item.attention_level.toUpperCase()}</span></header>
                  <p>{item.subjective_reason || "—"}</p>
                  <small>interest {item.interest_score.toFixed(2)} · {item.item.creator || item.item.source} · {stamp(item.last_exposed_at, zh)}</small>
                </article>
              ))}
              {exposures.length === 0 && <small>{zh ? "还没有 perception evidence。" : "No perception evidence yet."}</small>}
            </div>
          )}

          {view === "decisions" && (
            <div className="discovery-intelligence-list">
              {decisions.map((item) => (
                <article key={item.id}>
                  <header><strong>{item.item.title || item.item.url}</strong><span>{item.decision.toUpperCase()}</span></header>
                  <p>{item.motivation || "—"}</p>
                  <small>{item.mode.toUpperCase()} · confidence {item.confidence.toFixed(2)} · {stamp(item.created_at, zh)}</small>
                </article>
              ))}
              {decisions.length === 0 && <small>{zh ? "还没有 Discovery decision。" : "No Discovery decisions yet."}</small>}
            </div>
          )}

          {view === "shares" && (
            <div className="discovery-intelligence-list">
              {shares.map((item) => (
                <article key={item.id}>
                  <header><strong>{item.item.title || item.item.url}</strong><span>{item.status.toUpperCase()}</span></header>
                  <p>{item.motivation || item.draft_text || "—"}</p>
                  <small>{item.mode.toUpperCase()} · confidence {item.confidence.toFixed(2)} · {stamp(item.created_at, zh)}</small>
                  {item.last_error && <small className="deployment-inline-error">{item.last_error}</small>}
                  {item.status === "pending_review" && (
                    <div className="discovery-share-actions">
                      <button type="button" className="ink-button" disabled={loading} onClick={() => void resolveShare(item, "approve")}>{zh ? "批准" : "Approve"}</button>
                      <button type="button" className="paper-button" disabled={loading} onClick={() => void resolveShare(item, "reject")}>{zh ? "拒绝" : "Reject"}</button>
                    </div>
                  )}
                </article>
              ))}
              {shares.length === 0 && <small>{zh ? "还没有分享记录。" : "No share records yet."}</small>}
            </div>
          )}
        </>
      )}
    </section>
  );
}
