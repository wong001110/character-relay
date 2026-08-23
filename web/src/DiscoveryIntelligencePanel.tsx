import { useEffect, useMemo, useState } from "react";

import type { CharacterDeployment } from "./deploymentApi";
import { deploymentPresenceApi, type DeploymentPresenceView } from "./deploymentPresenceApi";
import {
  discoveryApi,
  type DiscoveryDecision,
  type DiscoveryExposure,
  type DiscoveryProfile,
  type DiscoverySession,
  type DiscoveryShare
} from "./discoveryApi";
import { pageCount, pageItems } from "./conversationPagination";
import { Pagination } from "./Pagination";

interface Props {
  deployments: CharacterDeployment[];
  zh: boolean;
}

type DiscoveryView = "overview" | "perception" | "decisions" | "shares";

const DISCOVERY_PAGE_SIZE = 12;

type DiscoveryCollection = "sessions" | "exposures" | "decisions" | "shares";

interface CursorState {
  page: number;
  cursor: string | null;
  nextCursor: string | null;
  hasMore: boolean;
  paged: boolean;
  history: Array<string | null>;
}

const initialCursorState = (): CursorState => ({
  page: 1,
  cursor: null,
  nextCursor: null,
  hasMore: false,
  paged: false,
  history: [null]
});

function instant(value: string): number {
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/iu.test(value);
  return Date.parse(hasZone ? value : `${value}Z`);
}

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = instant(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

function sessionReason(item: DiscoverySession, zh: boolean): string {
  const reason = item.reason || item.error || "";
  if (reason === "leisure_window_expired") {
    return zh
      ? "错过浏览时间窗口：这次计划没有在允许时间内开始，不代表来源故障。"
      : "Missed browsing window: this scheduled visit did not start in time; the source itself did not fail.";
  }
  if (reason === "discovery_profile_no_longer_allows_browsing") {
    return zh
      ? "计划已跳过：当前 Discovery 设置已不再允许这次浏览。"
      : "Skipped because the current Discovery policy no longer allows this visit.";
  }
  if (reason === "browsing_completed_with_social_intent") {
    return zh
      ? "浏览已完成，并产生了后续社交/分享意图。"
      : "Browsing completed and produced a follow-up social/share intent.";
  }
  if (reason === "browsing_completed") {
    return zh ? "浏览已完成。" : "Browsing completed.";
  }
  return reason || (zh ? "没有额外说明" : "No additional note");
}

function presenceLabel(value: DeploymentPresenceView | null, zh: boolean): string {
  if (!value) return zh ? "读取中" : "Loading";
  if (value.state === "browsing") {
    const activity = value.activity_type ? ` · ${value.activity_type}` : "";
    return `${zh ? "浏览中" : "Browsing"}${activity}`;
  }
  if (value.state === "sleeping") return zh ? "睡眠中" : "Sleeping";
  if (value.state === "busy") return zh ? "忙碌" : "Busy";
  return zh ? "空闲" : "Idle";
}

export function DiscoveryIntelligencePanel({ deployments, zh }: Props) {
  const [deploymentId, setDeploymentId] = useState(
    deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
  );
  const [profile, setProfile] = useState<DiscoveryProfile | null>(null);
  const [presence, setPresence] = useState<DeploymentPresenceView | null>(null);
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [exposures, setExposures] = useState<DiscoveryExposure[]>([]);
  const [decisions, setDecisions] = useState<DiscoveryDecision[]>([]);
  const [shares, setShares] = useState<DiscoveryShare[]>([]);
  const [sessionPage, setSessionPage] = useState(1);
  const [exposurePage, setExposurePage] = useState(1);
  const [decisionPage, setDecisionPage] = useState(1);
  const [sharePage, setSharePage] = useState(1);
  const [cursorState, setCursorState] = useState<Record<DiscoveryCollection, CursorState>>({
    sessions: initialCursorState(),
    exposures: initialCursorState(),
    decisions: initialCursorState(),
    shares: initialCursorState()
  });
  const [view, setView] = useState<DiscoveryView>("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedDeployment = deployments.find((item) => item.id === deploymentId) ?? null;
  const pendingShares = useMemo(
    () => shares.filter((item) => item.status === "pending_review"),
    [shares]
  );
  const activeSession = sessions.find((item) => item.status === "active") ?? null;
  const latestResult =
    sessions.find((item) => ["completed", "skipped", "failed"].includes(item.status)) ?? null;
  const metricSession = activeSession ?? sessions[0] ?? null;
  const sessionPages = cursorState.sessions.paged
    ? (cursorState.sessions.hasMore ? cursorState.sessions.page + 1 : cursorState.sessions.page)
    : fixturePageCount(sessions.length, sessionPage);
  const visibleSessions = useMemo(
    () => cursorState.sessions.paged ? sessions : pageItems(sessions, sessionPage, DISCOVERY_PAGE_SIZE),
    [cursorState.sessions.paged, sessions, sessionPage]
  );
  const exposurePages = cursorState.exposures.paged
    ? (cursorState.exposures.hasMore ? cursorState.exposures.page + 1 : cursorState.exposures.page)
    : fixturePageCount(exposures.length, exposurePage);
  const visibleExposures = useMemo(
    () => cursorState.exposures.paged ? exposures : pageItems(exposures, exposurePage, DISCOVERY_PAGE_SIZE),
    [cursorState.exposures.paged, exposures, exposurePage]
  );
  const decisionPages = cursorState.decisions.paged
    ? (cursorState.decisions.hasMore ? cursorState.decisions.page + 1 : cursorState.decisions.page)
    : fixturePageCount(decisions.length, decisionPage);
  const visibleDecisions = useMemo(
    () => cursorState.decisions.paged ? decisions : pageItems(decisions, decisionPage, DISCOVERY_PAGE_SIZE),
    [cursorState.decisions.paged, decisions, decisionPage]
  );
  const sharePages = cursorState.shares.paged
    ? (cursorState.shares.hasMore ? cursorState.shares.page + 1 : cursorState.shares.page)
    : fixturePageCount(shares.length, sharePage);
  const visibleShares = useMemo(
    () => cursorState.shares.paged ? shares : pageItems(shares, sharePage, DISCOVERY_PAGE_SIZE),
    [cursorState.shares.paged, shares, sharePage]
  );

  useEffect(() => {
    if (!deployments.some((item) => item.id === deploymentId)) {
      setDeploymentId(
        deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
      );
    }
  }, [deploymentId, deployments]);

  function fixturePageCount(total: number, page: number): number {
    return pageCount(total, DISCOVERY_PAGE_SIZE) || Math.max(1, page);
  }

  async function load() {
    if (!deploymentId) return;
    try {
      setLoading(true);
      setError("");
      const [nextProfile, nextPresence, nextSessions, nextExposures, nextDecisions, nextShares] = await Promise.all([
        discoveryApi.profile(deploymentId),
        deploymentPresenceApi.get(deploymentId),
        discoveryApi.sessions(deploymentId, { limit: DISCOVERY_PAGE_SIZE }),
        discoveryApi.exposures(deploymentId, { limit: DISCOVERY_PAGE_SIZE }),
        discoveryApi.decisions(deploymentId, { limit: DISCOVERY_PAGE_SIZE }),
        discoveryApi.shares(deploymentId, { limit: DISCOVERY_PAGE_SIZE })
      ]);
      setProfile(nextProfile);
      setPresence(nextPresence);
      setSessions(nextSessions.items);
      setExposures(nextExposures.items);
      setDecisions(nextDecisions.items);
      setShares(nextShares.items);
      setSessionPage(1);
      setExposurePage(1);
      setDecisionPage(1);
      setSharePage(1);
      setCursorState({
        sessions: { ...initialCursorState(), nextCursor: nextSessions.next_cursor, hasMore: nextSessions.has_more, paged: nextSessions.paged },
        exposures: { ...initialCursorState(), nextCursor: nextExposures.next_cursor, hasMore: nextExposures.has_more, paged: nextExposures.paged },
        decisions: { ...initialCursorState(), nextCursor: nextDecisions.next_cursor, hasMore: nextDecisions.has_more, paged: nextDecisions.paged },
        shares: { ...initialCursorState(), nextCursor: nextShares.next_cursor, hasMore: nextShares.has_more, paged: nextShares.paged }
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [deploymentId]);

  useEffect(() => {
    setSessionPage((current) => Math.min(Math.max(1, current), sessionPages));
  }, [sessionPages]);

  useEffect(() => {
    setExposurePage((current) => Math.min(Math.max(1, current), exposurePages));
  }, [exposurePages]);

  useEffect(() => {
    setDecisionPage((current) => Math.min(Math.max(1, current), decisionPages));
  }, [decisionPages]);

  useEffect(() => {
    setSharePage((current) => Math.min(Math.max(1, current), sharePages));
  }, [sharePages]);

  async function loadCollectionPage(collection: DiscoveryCollection, page: number) {
    const state = cursorState[collection];
    if (!state.paged) {
      if (collection === "sessions") setSessionPage(page);
      if (collection === "exposures") setExposurePage(page);
      if (collection === "decisions") setDecisionPage(page);
      if (collection === "shares") setSharePage(page);
      return;
    }
    if (page < 1 || (page > state.page && !state.hasMore)) return;
    const cursor = page === state.page
      ? state.cursor
      : page > state.page
        ? state.nextCursor
        : state.history[page - 1] ?? null;
    if (page > state.page && !cursor) return;
    try {
      setLoading(true);
      setError("");
      const next = collection === "sessions"
        ? await discoveryApi.sessions(deploymentId, { limit: DISCOVERY_PAGE_SIZE, cursor })
        : collection === "exposures"
          ? await discoveryApi.exposures(deploymentId, { limit: DISCOVERY_PAGE_SIZE, cursor })
          : collection === "decisions"
            ? await discoveryApi.decisions(deploymentId, { limit: DISCOVERY_PAGE_SIZE, cursor })
            : await discoveryApi.shares(deploymentId, { limit: DISCOVERY_PAGE_SIZE, cursor });
      if (collection === "sessions") setSessions(next.items as DiscoverySession[]);
      if (collection === "exposures") setExposures(next.items as DiscoveryExposure[]);
      if (collection === "decisions") setDecisions(next.items as DiscoveryDecision[]);
      if (collection === "shares") setShares(next.items as DiscoveryShare[]);
      setCursorState((current) => {
        const previous = current[collection];
        const history = page > previous.page
          ? [...previous.history, cursor]
          : previous.history.slice(0, page);
        return {
          ...current,
          [collection]: {
            page,
            cursor,
            nextCursor: next.next_cursor,
            hasMore: next.has_more,
            paged: next.paged,
            history
          }
        };
      });
      if (collection === "sessions") setSessionPage(page);
      if (collection === "exposures") setExposurePage(page);
      if (collection === "decisions") setDecisionPage(page);
      if (collection === "shares") setSharePage(page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function changeCollectionPage(collection: DiscoveryCollection, page: number) {
    if (!deploymentId || page === cursorState[collection].page) return;
    void loadCollectionPage(collection, page);
  }

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
          <span>Deployment</span>
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
                <article><span>{zh ? "当前状态" : "Current"}</span><strong>{presenceLabel(presence, zh)}</strong></article>
                <article><span>{zh ? "最近结果" : "Latest result"}</span><strong>{latestResult?.status?.toUpperCase() ?? "—"}</strong></article>
                <article><span>{zh ? "候选" : "Candidates"}</span><strong>{metricSession?.candidate_count ?? 0}</strong></article>
                <article><span>NOTICE</span><strong>{metricSession?.notice_count ?? 0}</strong></article>
                <article><span>OPEN</span><strong>{metricSession?.open_count ?? 0}</strong></article>
                <article><span>WATCH</span><strong>{metricSession?.watch_count ?? 0}</strong></article>
                <article><span>ENGAGE</span><strong>{metricSession?.engage_count ?? 0}</strong></article>
              </div>
              <small>
                {zh
                  ? "SKIPPED 表示某次计划没有执行；例如错过休闲浏览窗口。它不等于 YouTube / Bilibili 来源故障。"
                  : "SKIPPED means a scheduled visit did not execute, for example because its leisure window expired. It does not mean the YouTube/Bilibili source failed."}
              </small>
              <div className="discovery-intelligence-list">
                {visibleSessions.map((item) => (
                  <article key={item.id}>
                    <header><strong>{item.platform || item.source || "Discovery"}</strong><span>{item.status.toUpperCase()}</span></header>
                    <p>{sessionReason(item, zh)}</p>
                    <small>{stamp(item.started_at ?? item.scheduled_start_at, zh)} · {item.planned_duration_minutes} min</small>
                    {(item.reason || item.error) && (
                      <details>
                        <summary>{zh ? "运行证据" : "Runtime evidence"}</summary>
                        <small>{item.reason || item.error}</small>
                      </details>
                    )}
                  </article>
                ))}
                {sessions.length === 0 && <small>{zh ? "还没有 browsing session。" : "No browsing sessions yet."}</small>}
              </div>
              <Pagination page={sessionPage} pages={sessionPages} total={sessions.length} onPage={(page) => changeCollectionPage("sessions", page)} disabled={loading} />
            </>
          )}

          {view === "perception" && (
            <>
              <div className="discovery-intelligence-list">
                {visibleExposures.map((item) => (
                  <article key={item.id}>
                    <header><strong>{item.item.title || item.item.url}</strong><span>{item.attention_level.toUpperCase()}</span></header>
                    <p>{item.subjective_reason || "—"}</p>
                    <small>interest {item.interest_score.toFixed(2)} · {item.item.creator || item.item.source} · {stamp(item.last_exposed_at, zh)}</small>
                  </article>
                ))}
                {exposures.length === 0 && <small>{zh ? "还没有 perception evidence。" : "No perception evidence yet."}</small>}
              </div>
              <Pagination page={exposurePage} pages={exposurePages} total={exposures.length} onPage={(page) => changeCollectionPage("exposures", page)} disabled={loading} />
            </>
          )}

          {view === "decisions" && (
            <>
              <div className="discovery-intelligence-list">
                {visibleDecisions.map((item) => (
                  <article key={item.id}>
                    <header><strong>{item.item.title || item.item.url}</strong><span>{item.decision.toUpperCase()}</span></header>
                    <p>{item.motivation || "—"}</p>
                    <small>{item.mode.toUpperCase()} · confidence {item.confidence.toFixed(2)} · {stamp(item.created_at, zh)}</small>
                  </article>
                ))}
                {decisions.length === 0 && <small>{zh ? "还没有 Discovery decision。" : "No Discovery decisions yet."}</small>}
              </div>
              <Pagination page={decisionPage} pages={decisionPages} total={decisions.length} onPage={(page) => changeCollectionPage("decisions", page)} disabled={loading} />
            </>
          )}

          {view === "shares" && (
            <>
              <div className="discovery-intelligence-list">
                {visibleShares.map((item) => (
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
              <Pagination page={sharePage} pages={sharePages} total={shares.length} onPage={(page) => changeCollectionPage("shares", page)} disabled={loading} />
            </>
          )}
        </>
      )}
    </section>
  );
}
