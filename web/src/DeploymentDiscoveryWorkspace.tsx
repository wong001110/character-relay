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
import { PaperDrawer } from "./NotebookUI";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

type ObservatoryView = "overview" | "perception" | "decisions" | "shares";

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

function mutableProfile(profile: DiscoveryProfile) {
  return {
    mode: profile.mode,
    youtube_enabled: profile.youtube_enabled,
    bilibili_enabled: profile.bilibili_enabled,
    auto_share_enabled: profile.auto_share_enabled,
    daily_share_budget: profile.daily_share_budget,
    share_cooldown_minutes: profile.share_cooldown_minutes
  };
}

function sameProfile(left: DiscoveryProfile, right: DiscoveryProfile): boolean {
  return JSON.stringify(mutableProfile(left)) === JSON.stringify(mutableProfile(right));
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

function score(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "—";
}

export function DeploymentDiscoveryWorkspace({
  deploymentId,
  disabled = false,
  zh
}: Props) {
  const [persisted, setPersisted] = useState<DiscoveryProfile>(() => emptyProfile(deploymentId));
  const [draft, setDraft] = useState<DiscoveryProfile>(() => emptyProfile(deploymentId));
  const [lastEnabledMode, setLastEnabledMode] =
    useState<Exclude<DiscoveryMode, "off">>("shadow");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedNote, setSavedNote] = useState("");

  const [observatoryOpen, setObservatoryOpen] = useState(false);
  const [observatoryLoading, setObservatoryLoading] = useState(false);
  const [view, setView] = useState<ObservatoryView>("overview");
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [exposures, setExposures] = useState<DiscoveryExposure[]>([]);
  const [decisions, setDecisions] = useState<DiscoveryDecision[]>([]);
  const [shares, setShares] = useState<DiscoveryShare[]>([]);

  const dirty = !sameProfile(persisted, draft);
  const enabled = draft.mode !== "off";
  const runtimeEnabled = persisted.mode !== "off";
  const pendingShares = useMemo(
    () => shares.filter((item) => item.status === "pending_review"),
    [shares]
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setSavedNote("");
    discoveryApi
      .profile(deploymentId)
      .then((profile) => {
        if (!active) return;
        setPersisted(profile);
        setDraft(profile);
        if (profile.mode !== "off") setLastEnabledMode(profile.mode);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deploymentId]);

  function patch(values: Partial<DiscoveryProfile>) {
    setDraft((current) => ({ ...current, ...values }));
    setSavedNote("");
  }

  function toggleEnabled() {
    if (enabled) {
      if (draft.mode !== "off") setLastEnabledMode(draft.mode);
      patch({ mode: "off" });
    } else {
      patch({ mode: lastEnabledMode });
    }
  }

  function setMode(mode: Exclude<DiscoveryMode, "off">) {
    setLastEnabledMode(mode);
    patch({ mode });
  }

  async function saveChanges() {
    if (!dirty) return;
    try {
      setSaving(true);
      setError("");
      const saved = await discoveryApi.updateProfile(deploymentId, draft);
      setPersisted(saved);
      setDraft(saved);
      if (saved.mode !== "off") setLastEnabledMode(saved.mode);
      setSavedNote(
        zh
          ? "Discovery 设置已保存，运行时现在会使用这份配置。"
          : "Discovery settings saved. Runtime now uses this configuration."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function loadObservatory() {
    try {
      setObservatoryLoading(true);
      setError("");
      const [nextSessions, nextExposures, nextDecisions, nextShares] = await Promise.all([
        discoveryApi.sessions(deploymentId),
        discoveryApi.exposures(deploymentId),
        discoveryApi.decisions(deploymentId),
        discoveryApi.shares(deploymentId)
      ]);
      setSessions(nextSessions.items);
      setExposures(nextExposures.items);
      setDecisions(nextDecisions.items);
      setShares(nextShares.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setObservatoryLoading(false);
    }
  }

  function openObservatory() {
    setObservatoryOpen(true);
    void loadObservatory();
  }

  async function browse() {
    if (dirty) {
      setError(
        zh
          ? "请先保存 Discovery 设置，再执行手动浏览。"
          : "Save Discovery settings before running a manual browse."
      );
      return;
    }
    const platform = persisted.youtube_enabled
      ? "youtube"
      : persisted.bilibili_enabled
        ? "bilibili"
        : undefined;
    if (!platform) return;
    try {
      setObservatoryLoading(true);
      await discoveryApi.browse(deploymentId, platform);
      await loadObservatory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setObservatoryLoading(false);
    }
  }

  async function resolveShare(item: DiscoveryShare, action: "approve" | "reject") {
    try {
      setObservatoryLoading(true);
      if (action === "approve") await discoveryApi.approve(deploymentId, item.id);
      else await discoveryApi.reject(deploymentId, item.id);
      await loadObservatory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setObservatoryLoading(false);
    }
  }

  const latest = sessions[0];

  return (
    <>
      <section className="deployment-form-wide discovery-settings-sheet">
        <div className="deployment-form-divider discovery-settings-heading">
          <div>
            <strong>{zh ? "角色探索 / Discovery" : "Character Discovery"}</strong>
            <span>
              {zh
                ? "先完成选择，再统一保存。这里负责权限；浏览历史与判断记录放在 Observatory。"
                : "Choose first, then save once. This section controls permissions; browsing history and decisions live in the Observatory."}
            </span>
          </div>
          <label className="discovery-master-toggle">
            <input
              type="checkbox"
              checked={enabled}
              disabled={disabled || loading || saving}
              onChange={toggleEnabled}
            />
            <strong>{enabled ? "ON" : "OFF"}</strong>
          </label>
        </div>

        {error && <small className="deployment-inline-error">{error}</small>}

        <div className={`discovery-settings-grid${enabled ? "" : " is-disabled"}`}>
          <fieldset disabled={!enabled || disabled || loading || saving}>
            <legend>{zh ? "允许来源" : "Allowed sources"}</legend>
            <label>
              <input
                type="checkbox"
                checked={draft.youtube_enabled}
                onChange={() => patch({ youtube_enabled: !draft.youtube_enabled })}
              />
              <span>YouTube</span>
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.bilibili_enabled}
                disabled={!draft.bilibili_experimental_available}
                onChange={() => patch({ bilibili_enabled: !draft.bilibili_enabled })}
              />
              <span>Bilibili <em>EXPERIMENTAL</em></span>
            </label>
            {!draft.bilibili_experimental_available && (
              <small>
                {zh
                  ? "Bilibili 被系统级 Experimental 开关禁用。"
                  : "Bilibili is disabled by the system Experimental gate."}
              </small>
            )}
          </fieldset>

          <fieldset disabled={!enabled || disabled || loading || saving}>
            <legend>{zh ? "分享行为" : "Sharing behavior"}</legend>
            {(["shadow", "review", "auto"] as const).map((mode) => (
              <label key={mode}>
                <input
                  type="radio"
                  name={`discovery-mode-${deploymentId}`}
                  checked={draft.mode === mode}
                  onChange={() => setMode(mode)}
                />
                <span>{mode.toUpperCase()}</span>
              </label>
            ))}
            {draft.mode === "auto" && (
              <label>
                <input
                  type="checkbox"
                  checked={draft.auto_share_enabled}
                  onChange={() =>
                    patch({ auto_share_enabled: !draft.auto_share_enabled })
                  }
                />
                <span>{zh ? "允许此 Deployment AUTO 分享" : "Allow AUTO for this Deployment"}</span>
                {!draft.auto_global_enabled && (
                  <small>{zh ? "全局 AUTO 仍关闭" : "Global AUTO remains disabled"}</small>
                )}
              </label>
            )}
          </fieldset>

          <fieldset disabled={!enabled || disabled || loading || saving}>
            <legend>{zh ? "分享限制" : "Share limits"}</legend>
            <label>
              <span>{zh ? "每日预算" : "Daily budget"}</span>
              <input
                type="number"
                min={0}
                max={8}
                value={draft.daily_share_budget}
                onChange={(event) =>
                  patch({ daily_share_budget: Number(event.currentTarget.value) })
                }
              />
            </label>
            <label>
              <span>{zh ? "冷却（分钟）" : "Cooldown (minutes)"}</span>
              <input
                type="number"
                min={15}
                max={1440}
                value={draft.share_cooldown_minutes}
                onChange={(event) =>
                  patch({ share_cooldown_minutes: Number(event.currentTarget.value) })
                }
              />
            </label>
          </fieldset>
        </div>

        <div className="discovery-settings-actions">
          <div>
            <button type="button" className="paper-button" onClick={openObservatory}>
              {zh ? "打开 Discovery Observatory" : "Open Discovery Observatory"}
            </button>
            <small>
              {zh ? "已保存运行状态：" : "Persisted runtime: "}
              {persisted.mode.toUpperCase()}
            </small>
          </div>
          <div>
            {dirty && (
              <button
                type="button"
                className="text-button"
                disabled={saving}
                onClick={() => {
                  setDraft(persisted);
                  setSavedNote("");
                  setError("");
                }}
              >
                {zh ? "撤销修改" : "Discard changes"}
              </button>
            )}
            <button
              type="button"
              className="ink-button"
              disabled={!dirty || disabled || loading || saving}
              onClick={() => void saveChanges()}
            >
              {saving
                ? zh
                  ? "保存中…"
                  : "Saving…"
                : zh
                  ? "保存 Discovery 设置"
                  : "Save Discovery settings"}
            </button>
          </div>
        </div>
        {savedNote && <p className="success-note">{savedNote}</p>}
      </section>

      {observatoryOpen && (
        <PaperDrawer
          onClose={() => setObservatoryOpen(false)}
          ariaLabel="Discovery Observatory"
          className="discovery-observatory-drawer"
        >
          <section className="paper-sheet discovery-observatory-sheet">
            <div className="discovery-observatory-heading">
              <div>
                <span className="tape-label">DISCOVERY OBSERVATORY</span>
                <h2>
                  {zh
                    ? "这个角色最近在外部世界看到了什么"
                    : "What this Character has encountered outside Discord"}
                </h2>
                {dirty && (
                  <small>
                    {zh
                      ? "Deployment Editor 有未保存设置；这里仍按已保存配置显示运行状态。"
                      : "The Deployment Editor has unsaved settings; this view still reflects the persisted runtime configuration."}
                  </small>
                )}
              </div>
              <div>
                <button
                  type="button"
                  className="paper-button"
                  disabled={observatoryLoading}
                  onClick={() => void loadObservatory()}
                >
                  {zh ? "刷新" : "Refresh"}
                </button>
                <button
                  type="button"
                  className="paper-button"
                  disabled={
                    !runtimeEnabled ||
                    dirty ||
                    observatoryLoading ||
                    (!persisted.youtube_enabled && !persisted.bilibili_enabled)
                  }
                  onClick={() => void browse()}
                >
                  {zh ? "手动浏览" : "Run browse"}
                </button>
              </div>
            </div>

            <nav className="discovery-subtabs">
              {(["overview", "perception", "decisions", "shares"] as ObservatoryView[]).map(
                (item) => (
                  <button
                    key={item}
                    type="button"
                    className={view === item ? "is-active" : ""}
                    onClick={() => setView(item)}
                  >
                    {item}
                    {item === "shares" && pendingShares.length
                      ? ` (${pendingShares.length})`
                      : ""}
                  </button>
                )
              )}
            </nav>

            {view === "overview" && (
              <>
                <div className="discovery-metrics">
                  <article><span>{zh ? "状态" : "State"}</span><strong>{persisted.mode.toUpperCase()}</strong></article>
                  <article><span>{zh ? "候选" : "Candidates"}</span><strong>{latest?.candidate_count ?? 0}</strong></article>
                  <article><span>NOTICE</span><strong>{latest?.notice_count ?? 0}</strong></article>
                  <article><span>OPEN</span><strong>{latest?.open_count ?? 0}</strong></article>
                  <article><span>WATCH</span><strong>{latest?.watch_count ?? 0}</strong></article>
                  <article><span>ENGAGE</span><strong>{latest?.engage_count ?? 0}</strong></article>
                </div>
                <div className="discovery-list">
                  {sessions.map((item) => (
                    <article key={item.id}>
                      <strong>{item.platform || item.source || "Discovery"} · {item.status}</strong>
                      <span>{stamp(item.started_at ?? item.scheduled_start_at, zh)}</span>
                      <small>
                        {item.candidate_count} → {item.notice_count} → {item.open_count} →{" "}
                        {item.watch_count} → {item.engage_count}
                      </small>
                      {item.error && <small className="deployment-inline-error">{item.error}</small>}
                    </article>
                  ))}
                  {!observatoryLoading && sessions.length === 0 && (
                    <small>{zh ? "还没有浏览记录。" : "No browsing sessions yet."}</small>
                  )}
                </div>
              </>
            )}

            {view === "perception" && (
              <div className="discovery-list">
                {exposures.map((item) => (
                  <article key={item.id}>
                    <strong>{item.item.title || item.item.canonical_key}</strong>
                    <span>{item.attention_level.toUpperCase()} · {score(item.interest_score)}</span>
                    <small>{item.item.source} · {item.item.creator}</small>
                    <p>{item.subjective_reason || (zh ? "没有记录主观理由" : "No subjective reason recorded")}</p>
                  </article>
                ))}
                {!observatoryLoading && exposures.length === 0 && (
                  <small>{zh ? "还没有 Perception 记录。" : "No Discovery perception records yet."}</small>
                )}
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
                {!observatoryLoading && decisions.length === 0 && (
                  <small>{zh ? "还没有判断记录。" : "No Discovery decisions yet."}</small>
                )}
              </div>
            )}

            {view === "shares" && (
              <div className="discovery-list">
                {shares.map((item) => (
                  <article key={item.id}>
                    <strong>{item.status} · {item.motivation || "—"}</strong>
                    <span>{score(item.confidence)} · {stamp(item.created_at, zh)}</span>
                    <small>{item.item.title || item.item.canonical_key}</small>
                    {item.draft_text && <p>{item.draft_text}</p>}
                    {item.status === "pending_review" && (
                      <div>
                        <button
                          type="button"
                          className="paper-button"
                          disabled={observatoryLoading}
                          onClick={() => void resolveShare(item, "approve")}
                        >
                          {zh ? "批准" : "Approve"}
                        </button>
                        <button
                          type="button"
                          className="text-button"
                          disabled={observatoryLoading}
                          onClick={() => void resolveShare(item, "reject")}
                        >
                          {zh ? "拒绝" : "Reject"}
                        </button>
                      </div>
                    )}
                    {item.last_error && (
                      <small className="deployment-inline-error">{item.last_error}</small>
                    )}
                  </article>
                ))}
                {!observatoryLoading && shares.length === 0 && (
                  <small>{zh ? "还没有分享记录。" : "No Discovery shares yet."}</small>
                )}
              </div>
            )}
          </section>
        </PaperDrawer>
      )}
    </>
  );
}
