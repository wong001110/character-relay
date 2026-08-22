import { useEffect, useMemo, useRef, useState } from "react";

import type { CharacterCard } from "./api";
import {
  Button,
  EmptyState,
  FormField,
  IconButton,
  InspectorSection,
  PaperTab,
  SearchField,
  Select,
  Spinner,
  Stamp,
  StatusIndicator,
  type StatusTone,
  StickyLabel,
  StickyNote,
  Toast
} from "./components/ui";
import {
  deploymentApi,
  type DiscordServerProfile
} from "./deploymentApi";
import {
  discordDebugCaptureApi,
  type DiscordDebugCaptureOutcome,
  type DiscordDebugCaptureRecordDetail,
  type DiscordDebugCaptureRecordSummary,
  type DiscordDebugCaptureSession,
  type DiscordDebugCaptureTtlMinutes
} from "./discordDebugCaptureApi";
import { useI18n } from "./i18n";
import { formatPortalTimestamp } from "./portalTime";
import {
  providerTraceApi,
  type ProviderTraceSummary,
  type ProviderTraceView
} from "./providerTraceApi";
import {
  runtimeTraceApi,
  type RuntimeTraceEvent,
  type RuntimeTraceSummary,
  type RuntimeTraceView
} from "./runtimeTraceApi";

type NotebookTab = "behavior" | "flow" | "state" | "raw";
type TurnFilter = "all" | "character";
type DebugAccess = "checking" | "allowed" | "denied";

interface Props {
  cards: CharacterCard[];
}

interface ProjectedStep {
  key: string;
  nodeName: string;
  nodeKind: string;
  status: string;
  startedAt: string;
  completedAt: string;
  durationMs: number | null;
  changedKeys: string[];
  metadata: Array<[string, string]>;
  error: string;
}

type NotebookEntry =
  | {
      kind: "character";
      id: string;
      createdAt: string;
      run: RuntimeTraceSummary;
    };

const NODE_COPY: Record<string, { en: string; zh: string; icon: string }> = {
  turn_resolve: { en: "Resolve target", zh: "解析目标", icon: "◎" },
  turn_context: { en: "Build context", zh: "建立上下文", icon: "▤" },
  turn_model: { en: "Character generation", zh: "角色生成", icon: "✦" },
  turn_tool_execution: { en: "Tool execution", zh: "工具执行", icon: "⚒" },
  turn_media_epistemic: { en: "Media note", zh: "媒体观察", icon: "◉" },
  turn_smart_output: { en: "Smart Output validation / repair", zh: "Smart Output 验证 / 格式修复", icon: "✧" },
  turn_authority: { en: "Runtime authority", zh: "Runtime 最终授权", icon: "♢" }
};

const TAB_TONES = {
  behavior: "yellow",
  flow: "blue",
  state: "mint",
  raw: "lavender"
} as const;

const DEBUG_TTL_OPTIONS: Array<{
  value: DiscordDebugCaptureTtlMinutes;
  en: string;
  zh: string;
}> = [
  { value: 15, en: "15 min", zh: "15 分钟" },
  { value: 60, en: "1 hour", zh: "1 小时" },
  { value: 1440, en: "24 hours", zh: "24 小时" }
];

function metadataRecord(values: Array<[string, string]>): Record<string, string> {
  return Object.fromEntries(values);
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function durationLabel(value: number | null): string {
  if (value === null) return "…";
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)}s`;
  return `${value}ms`;
}

function shortId(value: string): string {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function statusTone(value: string): StatusTone {
  if (["completed", "succeeded", "selected", "ready"].includes(value)) return "success";
  if (["failed", "error", "rejected"].includes(value)) return "danger";
  if (["running", "pending"].includes(value)) return "info";
  if (["cancelled", "skipped", "silent"].includes(value)) return "neutral";
  return "warning";
}

function stampVariant(value: string): "success" | "danger" | "info" | "accent" {
  if (["completed", "succeeded", "selected"].includes(value)) return "success";
  if (["failed", "rejected"].includes(value)) return "danger";
  if (["running", "pending"].includes(value)) return "info";
  return "accent";
}

function projectSteps(events: RuntimeTraceEvent[]): ProjectedStep[] {
  const steps: ProjectedStep[] = [];
  for (const event of events) {
    if (event.status === "started") {
      steps.push({
        key: `${event.id}`,
        nodeName: event.node_name,
        nodeKind: event.node_kind,
        status: "running",
        startedAt: event.created_at,
        completedAt: "",
        durationMs: null,
        changedKeys: [],
        metadata: [],
        error: ""
      });
      continue;
    }
    const open = [...steps]
      .reverse()
      .find((step) => step.nodeName === event.node_name && step.status === "running");
    if (open) {
      open.status = event.status;
      open.completedAt = event.created_at;
      open.durationMs = Math.max(0, timestampMs(event.created_at) - timestampMs(open.startedAt));
      open.changedKeys = event.changed_keys;
      open.metadata = event.metadata;
      open.error = event.error;
      continue;
    }
    steps.push({
      key: `${event.id}`,
      nodeName: event.node_name,
      nodeKind: event.node_kind,
      status: event.status,
      startedAt: event.created_at,
      completedAt: event.created_at,
      durationMs: 0,
      changedKeys: event.changed_keys,
      metadata: event.metadata,
      error: event.error
    });
  }
  return steps;
}

function bytesLabel(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function countdownLabel(expiresAt: string, now: number, zh: boolean): string {
  const remaining = Math.max(0, timestampMs(expiresAt) - now);
  if (!remaining) return zh ? "已到期" : "Expired";
  const totalSeconds = Math.ceil(remaining / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours) return `${hours}h ${minutes}m ${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

function debugOutcomeTone(outcome: DiscordDebugCaptureOutcome): StatusTone {
  if (outcome === "succeeded") return "success";
  if (outcome === "provider_error") return "danger";
  if (outcome === "conflict") return "warning";
  return "info";
}

function debugOutcomeLabel(outcome: DiscordDebugCaptureOutcome, zh: boolean): string {
  if (!zh) return outcome.replace("_", " ");
  if (outcome === "succeeded") return "成功";
  if (outcome === "conflict") return "冲突";
  if (outcome === "provider_error") return "Provider 错误";
  return "等待结果";
}

export function BehaviorNotebook({ cards }: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [runs, setRuns] = useState<RuntimeTraceSummary[]>([]);
  const [providerTraces, setProviderTraces] = useState<ProviderTraceSummary[]>([]);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RuntimeTraceView | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<ProviderTraceView | null>(null);
  const [tab, setTab] = useState<NotebookTab>("behavior");
  const [filter, setFilter] = useState<TurnFilter>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [debugAccess, setDebugAccess] = useState<DebugAccess>("checking");
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [debugProfiles, setDebugProfiles] = useState<DiscordServerProfile[]>([]);
  const [debugProfilesLoading, setDebugProfilesLoading] = useState(false);
  const [debugProfileError, setDebugProfileError] = useState<string | null>(null);
  const [debugProfileId, setDebugProfileId] = useState("");
  const [debugTtl, setDebugTtl] = useState<DiscordDebugCaptureTtlMinutes>(15);
  const [debugSession, setDebugSession] = useState<DiscordDebugCaptureSession | null>(null);
  const [debugRecords, setDebugRecords] = useState<DiscordDebugCaptureRecordSummary[]>([]);
  const [debugRecordTotal, setDebugRecordTotal] = useState(0);
  const [debugRecordDetail, setDebugRecordDetail] = useState<DiscordDebugCaptureRecordDetail | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugWorking, setDebugWorking] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);
  const [debugNow, setDebugNow] = useState(() => Date.now());
  const controllerRef = useRef<AbortController | null>(null);

  const entries = useMemo<NotebookEntry[]>(() => {
    const characterEntries: NotebookEntry[] = runs.map((run) => ({
      kind: "character",
      id: `character:${run.graph_run_id}`,
      createdAt: run.created_at,
      run
    }));
    return characterEntries.sort(
      (left, right) => timestampMs(right.createdAt) - timestampMs(left.createdAt)
    );
  }, [runs]);

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.id === selectedEntryId) ?? null,
    [entries, selectedEntryId]
  );

  async function loadRuns() {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    try {
      const [runtimePage, providerPage] = await Promise.all([
        runtimeTraceApi.list({ limit: 80, graphName: "character_turn", signal: controller.signal }),
        providerTraceApi.list({ limit: 100, signal: controller.signal })
      ]);
      if (controller.signal.aborted) return;
      setRuns(runtimePage.items);
      setProviderTraces(providerPage.items);
      const newestRun = runtimePage.items[0];
      const nextId = newestRun ? `character:${newestRun.graph_run_id}` : null;
      setSelectedEntryId((current) => current ?? nextId);
      setError(null);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadRuns();
    return () => controllerRef.current?.abort();
  }, []);

  useEffect(() => {
    let active = true;
    void discordDebugCaptureApi
      .access()
      .then((allowed) => {
        if (!active) return;
        setDebugAccess(allowed ? "allowed" : "denied");
        if (!allowed) return;
        setDebugProfilesLoading(true);
        void deploymentApi
          .listDiscordServerProfiles()
          .then((profiles) => {
            if (active) setDebugProfiles(profiles);
          })
          .catch((reason) => {
            if (active) setDebugProfileError(reason instanceof Error ? reason.message : String(reason));
          })
          .finally(() => {
            if (active) setDebugProfilesLoading(false);
          });
      })
      .catch(() => {
        if (active) setDebugAccess("denied");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!debugPanelOpen || debugSession?.status !== "active") return;
    setDebugNow(Date.now());
    const timer = window.setInterval(() => setDebugNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [debugPanelOpen, debugSession?.status]);

  useEffect(() => {
    setDebugRecordDetail(null);
    setDebugRecords([]);
    setDebugRecordTotal(0);
    setDebugSession(null);
    setDebugError(null);
    if (!debugPanelOpen || !debugProfileId) return;
    let active = true;
    setDebugLoading(true);
    void discordDebugCaptureApi
      .currentSession(debugProfileId)
      .then(async (session) => {
        if (!active) return;
        setDebugSession(session);
        if (!session) return;
        const page = await discordDebugCaptureApi.listRecords(session.id);
        if (!active) return;
        setDebugRecords(page.items);
        setDebugRecordTotal(page.total);
      })
      .catch((reason) => {
        if (active) setDebugError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setDebugLoading(false);
      });
    return () => {
      active = false;
    };
  }, [debugPanelOpen, debugProfileId]);

  useEffect(() => {
    setSelectedProvider(null);
    setSelectedRun(null);
    if (selectedEntry?.kind !== "character") return;
    const controller = new AbortController();
    void runtimeTraceApi
      .detail(selectedEntry.run.graph_run_id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSelectedRun(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => controller.abort();
  }, [selectedEntry]);

  const visibleEntries = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return entries.filter((entry) => {
      if (filter !== "all" && entry.kind !== filter) return false;
      if (!needle) return true;
      const card = cards.find((item) => item.id === entry.run.character_card_id);
      return [entry.run.graph_run_id, entry.run.operation_id, entry.run.deployment_id, card?.display_name ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [cards, entries, filter, query]);

  async function inspectProvider(traceId: string) {
    try {
      setDebugPanelOpen(false);
      setDebugRecordDetail(null);
      setSelectedProvider(await providerTraceApi.detail(traceId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function refreshDebugRecords(sessionId: string) {
    setDebugLoading(true);
    setDebugError(null);
    setDebugRecordDetail(null);
    try {
      const page = await discordDebugCaptureApi.listRecords(sessionId);
      setDebugRecords(page.items);
      setDebugRecordTotal(page.total);
      const current = debugProfileId
        ? await discordDebugCaptureApi.currentSession(debugProfileId)
        : null;
      if (current) setDebugSession(current);
    } catch (reason) {
      setDebugError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDebugLoading(false);
    }
  }

  async function startDebugSession() {
    if (!debugProfileId) return;
    setDebugWorking(true);
    setDebugError(null);
    setDebugRecordDetail(null);
    try {
      const session = await discordDebugCaptureApi.startSession(debugProfileId, debugTtl);
      setDebugSession(session);
      setDebugRecords([]);
      setDebugRecordTotal(0);
      setDebugNow(Date.now());
    } catch (reason) {
      setDebugError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDebugWorking(false);
    }
  }

  async function stopDebugSession() {
    if (!debugSession) return;
    const confirmed = window.confirm(
      zh
        ? "停止这次临时捕获？已经捕获的记录会保留到清除或进程重启。"
        : "Stop this temporary capture? Existing records remain until cleared or the process restarts."
    );
    if (!confirmed) return;
    setDebugWorking(true);
    setDebugError(null);
    try {
      setDebugSession(await discordDebugCaptureApi.stopSession(debugSession.id));
    } catch (reason) {
      setDebugError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDebugWorking(false);
    }
  }

  async function clearDebugRecords() {
    if (!debugSession) return;
    const confirmed = window.confirm(
      zh
        ? "永久清除这次捕获的所有敏感记录？此操作无法撤销。"
        : "Permanently clear every sensitive record in this capture? This cannot be undone."
    );
    if (!confirmed) return;
    setDebugWorking(true);
    setDebugError(null);
    try {
      await discordDebugCaptureApi.clearRecords(debugSession.id);
      setDebugRecordDetail(null);
      setDebugRecords([]);
      setDebugRecordTotal(0);
      const current = await discordDebugCaptureApi.currentSession(debugSession.server_profile_id);
      if (current) setDebugSession(current);
    } catch (reason) {
      setDebugError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDebugWorking(false);
    }
  }

  async function revealDebugRecord(recordId: string) {
    setDebugWorking(true);
    setDebugError(null);
    setDebugRecordDetail(null);
    try {
      setDebugRecordDetail(await discordDebugCaptureApi.recordDetail(recordId));
    } catch (reason) {
      setDebugError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDebugWorking(false);
    }
  }

  function renderCharacterTurn() {
    if (selectedEntry?.kind !== "character") return null;
    if (!selectedRun) {
      return (
        <main className="behavior-notebook-page">
          <EmptyState
            className="behavior-loading-note"
            illustration={<Spinner label={zh ? "正在载入角色回合" : "Loading character turn"} />}
            title={zh ? "正在翻开角色回合…" : "Opening Character Turn…"}
          />
        </main>
      );
    }
    const steps = projectSteps(selectedRun.events);
    const card = cards.find((item) => item.id === selectedRun.character_card_id) ?? null;
    const runProviders = providerTraces.filter((item) => item.graph_run_id === selectedRun.graph_run_id);
    const runStart = steps[0]?.startedAt ?? selectedRun.created_at;
    const runEnd = [...steps].reverse().find((step) => step.completedAt)?.completedAt ?? selectedRun.updated_at;
    const totalMs = Math.max(0, timestampMs(runEnd) - timestampMs(runStart));
    const modelSteps = steps.filter((step) => step.nodeName === "turn_model" && step.status === "completed");
    const toolSteps = steps.filter((step) => step.nodeName === "turn_tool_execution" && step.status === "completed");
    const contextMeta = metadataRecord(steps.find((step) => step.nodeName === "turn_context")?.metadata ?? []);
    const authorityMeta = metadataRecord([...steps].reverse().find((step) => step.nodeName === "turn_authority")?.metadata ?? []);
    const mediaMeta = metadataRecord([...steps].reverse().find((step) => step.nodeName === "turn_media_epistemic")?.metadata ?? []);

    const renderFlow = () => (
      <section className="behavior-flow-stack">
        <div className="behavior-section-title"><span className="behavior-doodle">✿</span><h3>{zh ? "执行流程" : "Execution flow"}</h3></div>
        {steps.map((step, index) => {
          const copy = NODE_COPY[step.nodeName] ?? { en: step.nodeName, zh: step.nodeName, icon: "○" };
          const meta = metadataRecord(step.metadata);
          const providers = runProviders.filter((item) => item.runtime_node === step.nodeName);
          const smartRejected = step.nodeName === "turn_smart_output" && (meta.resolution ?? "").startsWith("invalid_smart_output:");
          return (
            <article className={`behavior-step behavior-kind-${step.nodeKind}`} key={step.key}>
              <div className="behavior-step-number">{index + 1}</div>
              <div className="behavior-step-card">
                <header>
                  <div><span className="behavior-step-icon" aria-hidden="true">{copy.icon}</span><strong>{step.nodeName}</strong><small>{zh ? copy.zh : copy.en}</small></div>
                  <div className="behavior-step-status">
                    <StatusIndicator tone={statusTone(step.status)} className={`behavior-status behavior-status-${step.status}`}>
                      {step.status}
                    </StatusIndicator>
                    <b>{durationLabel(step.durationMs)}</b>
                  </div>
                </header>
                {Object.keys(meta).length > 0 && <div className="behavior-meta-chips">{Object.entries(meta).slice(0, 8).map(([key, value]) => <span key={key}><small>{key}</small>{value || "—"}</span>)}</div>}
                {providers.map((provider, providerIndex) => (
                  <button type="button" className="behavior-provider-receipt" key={provider.trace_id} onClick={() => void inspectProvider(provider.trace_id)}>
                    <span>{step.nodeName === "turn_smart_output" ? (zh ? `格式修复 API #${providerIndex + 1}` : `Format-repair API #${providerIndex + 1}`) : `Provider API #${providerIndex + 1}`}</span>
                    <strong>{provider.response_model || provider.request_model || "Model call"}</strong>
                    <small>{durationLabel(provider.latency_ms)} · {provider.input_tokens ?? "—"} → {provider.output_tokens ?? "—"} tokens</small>
                    <StatusIndicator tone={statusTone(provider.status)} className={`behavior-status behavior-status-${provider.status}`}>
                      {provider.status === "succeeded" ? "API SUCCESS" : provider.status}
                    </StatusIndicator>
                  </button>
                ))}
                {step.nodeName === "turn_smart_output" && (
                  <div className={`behavior-output-verdict ${smartRejected ? "is-rejected" : "is-accepted"}`}>
                    <strong>{smartRejected ? (zh ? "Smart Output 被拒绝" : "SMART OUTPUT REJECTED") : (zh ? "Smart Output 已通过验证" : "SMART OUTPUT ACCEPTED")}</strong>
                    <span>{smartRejected ? (zh ? "原始 Provider response 没有获得 Runtime 输出权限 · NOT DELIVERED" : "Raw provider response was not authorized · NOT DELIVERED") : (zh ? "下一步仍需 Runtime authority 最终授权" : "Runtime authority still decides final delivery")}</span>
                  </div>
                )}
                {step.nodeName === "turn_authority" && (
                  <div className="behavior-authority-verdict"><small>{zh ? "最终平台行为" : "FINAL PLATFORM ACTION"}</small><strong>{meta.action || selectedRun.status}</strong><span>{meta.reason || "—"}</span></div>
                )}
                {step.nodeName === "turn_tool_execution" && <div className="behavior-tool-ticket"><span>{zh ? "工具票据" : "Tool ticket"}</span><strong>{meta.executed_count ?? "0"} {zh ? "个工具已执行" : "tool(s) executed"}</strong></div>}
                {step.nodeName === "turn_media_epistemic" && <div className="behavior-media-note"><span>{zh ? "媒体便签" : "Media note"}</span><strong>{meta.actual_perception || "—"}</strong><small>{meta.response_stance ? `${zh ? "姿态" : "stance"}: ${meta.response_stance}` : ""}</small></div>}
                {step.error && <Toast tone="danger" title={zh ? "Runtime step error" : "Runtime step error"}>{step.error}</Toast>}
              </div>
            </article>
          );
        })}
        {steps.length > 0 && <Stamp className="behavior-end-stamp" variant="accent">END OF TURN · ᓚᘏᗢ</Stamp>}
      </section>
    );

    return (
      <main className="behavior-notebook-page">
        <header className="behavior-notebook-header">
          <div className={`behavior-polaroid portrait-${card?.portrait_variant ?? "lavender"}`}><div className="behavior-polaroid-photo"><img src="/assets/character-silhouette.svg" alt="" /></div><span>{card?.display_name || "Character"} ♡</span></div>
          <div className="behavior-heading-copy">
            <span className="portal-v2-tape">CHARACTER TURN NOTEBOOK</span>
            <h2>{card ? `${card.display_name} ${zh ? "进入了角色 Runtime" : "entered Character Runtime"}` : (zh ? "角色回合" : "Character turn")}</h2>
            <p>Discord · {formatPortalTimestamp(selectedRun.created_at, zh)} → {formatPortalTimestamp(selectedRun.updated_at, zh)} · {durationLabel(totalMs)}</p>
            <nav className="behavior-tabs" role="tablist" aria-label={zh ? "观察视图" : "Observation view"}>
              {(["behavior", "flow", "state", "raw"] as NotebookTab[]).map((item) => (
                <PaperTab
                  type="button"
                  key={item}
                  tone={TAB_TONES[item]}
                  active={tab === item}
                  className={tab === item ? "is-active" : ""}
                  onClick={() => setTab(item)}
                >
                  {item === "behavior" ? "✿ " : item === "flow" ? "↝ " : item === "state" ? "⇄ " : "▤ "}
                  {item === "behavior" ? (zh ? "行为" : "Behavior") : item === "flow" ? "Flow" : item === "state" ? "State" : "Raw"}
                </PaperTab>
              ))}
            </nav>
          </div>
          <Stamp className={`behavior-completed-stamp stamp-${selectedRun.status}`} variant={stampVariant(selectedRun.status)}>
            {selectedRun.status}
          </Stamp>
        </header>
        <div className="behavior-notebook-body">
          <div className="behavior-main-column">
            {tab === "behavior" && (
              <>
                <section className="behavior-summary-row">
                  <StickyNote className="behavior-sticky behavior-sticky-yellow" variant="note" size="lg">
                    <span>{zh ? "行为摘要" : "Behavior summary"} ✧</span>
                    <ul>
                      <li>{zh ? `执行了 ${steps.length} 个 Runtime 步骤。` : `${steps.length} Runtime steps were observed.`}</li>
                      <li>{zh ? `正式 Character generation ${modelSteps.length} 次。` : `${modelSteps.length} Character generation step(s).`}</li>
                      <li>{runProviders.filter((item) => item.runtime_node === "turn_smart_output").length ? (zh ? "Smart Output 曾触发格式修复 Provider call。" : "Smart Output invoked a format-repair provider call.") : (zh ? "没有额外格式修复模型调用。" : "No extra format-repair model call.")}</li>
                      <li>{zh ? `最终 Runtime authority = ${authorityMeta.action || selectedRun.status}。` : `Final Runtime authority = ${authorityMeta.action || selectedRun.status}.`}</li>
                    </ul>
                  </StickyNote>
                  <StickyNote className="behavior-sticky behavior-sticky-blue" variant="system" size="lg">
                    <span>{zh ? "这一轮的证据" : "Evidence from this turn"}</span>
                    <div className="behavior-evidence-grid">
                      <p><small>RAG</small><strong>{contextMeta.rag_pipeline || "—"}</strong></p>
                      <p><small>Provider API</small><strong>{runProviders.length}</strong></p>
                      <p><small>Tools</small><strong>{toolSteps.length}</strong></p>
                      <p><small>Outcome</small><strong>{authorityMeta.action || selectedRun.status}</strong></p>
                    </div>
                  </StickyNote>
                </section>
                {renderFlow()}
              </>
            )}
            {tab === "flow" && renderFlow()}
            {tab === "state" && (
              <InspectorSection
                className="behavior-state-board"
                eyebrow={zh ? "状态变化" : "State changes"}
                title={zh ? "State 变化索引" : "State change index"}
                density="compact"
              >
                {steps.filter((step) => step.changedKeys.length).map((step) => (
                  <article key={step.key}>
                    <strong>{step.nodeName}</strong>
                    <div>{step.changedKeys.map((key) => <span key={key}>{key}</span>)}</div>
                  </article>
                ))}
              </InspectorSection>
            )}
            {tab === "raw" && (
              <InspectorSection
                className="behavior-raw-sheet"
                eyebrow={zh ? "档案袋" : "Archive sheet"}
                title="Raw Runtime Trace"
                density="compact"
              >
                <pre>{JSON.stringify(selectedRun, null, 2)}</pre>
              </InspectorSection>
            )}
          </div>
          <aside className="behavior-observation-margin">
            <InspectorSection
              className="behavior-margin-card observation-card"
              eyebrow="Observation"
              title={zh ? "这一轮发生了什么" : "What happened this turn"}
              density="compact"
            >
              <dl>
                <div><dt>{zh ? "模型步骤" : "Model steps"}</dt><dd>{modelSteps.length}</dd></div>
                <div><dt>{zh ? "格式修复" : "Format repair"}</dt><dd>{runProviders.filter((item) => item.runtime_node === "turn_smart_output").length}</dd></div>
                <div><dt>{zh ? "Provider API" : "Provider API"}</dt><dd>{runProviders.length}</dd></div>
                <div><dt>{zh ? "总耗时" : "Total latency"}</dt><dd>{durationLabel(totalMs)}</dd></div>
              </dl>
              <div className="behavior-margin-pills">
                <span>RAG · {contextMeta.rag_pipeline || "—"}</span>
                <span>Media · {mediaMeta.actual_perception || "—"}</span>
                <span>Authority · {authorityMeta.action || selectedRun.status}</span>
              </div>
            </InspectorSection>
            {runProviders.length > 0 && (
              <InspectorSection
                className="behavior-margin-card provider-card"
                eyebrow="Technical evidence"
                title="Provider API"
                density="compact"
              >
                {runProviders.map((provider, index) => (
                  <button type="button" key={provider.trace_id} onClick={() => void inspectProvider(provider.trace_id)}>
                    <small>#{index + 1} · {provider.runtime_node || provider.category}</small>
                    <strong>{provider.response_model || provider.request_model}</strong>
                    <span>{provider.status === "succeeded" ? "API SUCCESS" : provider.status} · {durationLabel(provider.latency_ms)}</span>
                  </button>
                ))}
              </InspectorSection>
            )}
            <InspectorSection
              className="behavior-margin-card operation-card"
              eyebrow="Trace identity"
              title="Operation"
              density="compact"
            >
              <p>{shortId(selectedRun.operation_id)}</p>
              <small>{shortId(selectedRun.graph_run_id)}</small>
            </InspectorSection>
          </aside>
        </div>
      </main>
    );
  }

  const selectedDebugProfile = debugProfiles.find((profile) => profile.id === debugProfileId) ?? null;
  const debugSessionActive = debugSession?.status === "active";

  return (
    <div className="behavior-notebook-shell">
      <aside className="behavior-run-sidebar">
        <div className="behavior-side-title">
          <span className="portal-v2-tape">ALL BEHAVIOR TURNS</span>
          <IconButton className="behavior-refresh" type="button" onClick={() => void loadRuns()} aria-label={zh ? "刷新" : "Refresh"}>↻</IconButton>
        </div>
        <div className="behavior-turn-filters">
          {(["all", "character"] as TurnFilter[]).map((value) => (
            <Button
              type="button"
              key={value}
              variant={filter === value ? "secondary" : "ghost"}
              size="sm"
              className={filter === value ? "is-active" : ""}
              onClick={() => setFilter(value)}
            >
              {value === "all" ? (zh ? "全部" : "All") : (zh ? "角色" : "Character")}
            </Button>
          ))}
        </div>
        <SearchField
          className="behavior-run-search"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          label={zh ? "搜索行为回合" : "Search behavior turns"}
          placeholder={zh ? "搜索角色、来源消息 ID 或 reason…" : "Search character, source message ID, or reason…"}
        />
        {debugAccess === "allowed" && (
          <Button
            className={`behavior-debug-open ${debugPanelOpen ? "is-active" : ""}`}
            variant={debugPanelOpen ? "secondary" : "ghost"}
            size="sm"
            aria-expanded={debugPanelOpen}
            onClick={() => {
              setSelectedProvider(null);
              setDebugPanelOpen((open) => !open);
            }}
          >
            <span aria-hidden="true">⌁</span>
            {zh ? "Runtime 临时捕获" : "Runtime ingress capture"}
          </Button>
        )}
        <div className="behavior-run-list">
          {visibleEntries.map((entry) => {
            const runCard = cards.find((item) => item.id === entry.run.character_card_id);
            return (
              <button type="button" key={entry.id} className={selectedEntryId === entry.id ? "is-active" : ""} onClick={() => setSelectedEntryId(entry.id)}>
                <span className={`behavior-mini-avatar portrait-${runCard?.portrait_variant ?? "lavender"}`}>{runCard?.display_name.slice(0, 1) || "C"}</span>
                <span className="behavior-run-copy">
                  <strong>{runCard?.display_name || (zh ? "角色回合" : "Character turn")}</strong>
                  <small>{formatPortalTimestamp(entry.createdAt, zh)}</small>
                  <em>{zh ? "角色 Runtime" : "Character Runtime"} · {entry.run.event_count} events</em>
                </span>
                <StatusIndicator tone={statusTone(entry.run.status)} className={`behavior-status behavior-status-${entry.run.status}`}>
                  {entry.run.status}
                </StatusIndicator>
              </button>
            );
          })}
          {!loading && visibleEntries.length === 0 && (
            <EmptyState
              className="behavior-empty"
              title={zh ? "还没有可观察的行为回合。" : "No observable behavior turns yet."}
              description={query ? (zh ? "试试更短的搜索词。" : "Try a shorter search query.") : undefined}
            />
          )}
        </div>
      </aside>

      {error && (
        <Toast className="behavior-page-error" tone="danger" title={zh ? "Behavior Notebook error" : "Behavior Notebook error"}>
          {error}
        </Toast>
      )}
      {!selectedEntry ? (
        <main className="behavior-notebook-page">
          <EmptyState
            className="behavior-loading-note"
            illustration={loading ? <Spinner label={zh ? "正在载入行为手帐" : "Loading behavior notebook"} /> : undefined}
            title={loading ? (zh ? "正在翻开行为手帐…" : "Opening the behavior notebook…") : (zh ? "选择一个行为回合。" : "Select a behavior turn.")}
          />
        </main>
      ) : renderCharacterTurn()}

      {selectedProvider && (
        <aside className="behavior-provider-inspector">
          <div className="behavior-provider-inspector-top">
            <div>
              <StickyLabel variant="link">PROVIDER API RECEIPT</StickyLabel>
              <h3>{selectedProvider.response_model || selectedProvider.request_model}</h3>
              <p>{selectedProvider.runtime_node || selectedProvider.category} · {durationLabel(selectedProvider.latency_ms)}</p>
            </div>
            <IconButton type="button" onClick={() => setSelectedProvider(null)} aria-label={zh ? "关闭 Provider 票据" : "Close provider receipt"}>×</IconButton>
          </div>
          <dl>
            <div><dt>API status</dt><dd><StatusIndicator tone={statusTone(selectedProvider.status)}>{selectedProvider.status}</StatusIndicator></dd></div>
            <div><dt>Tokens</dt><dd>{selectedProvider.input_tokens ?? "—"} → {selectedProvider.output_tokens ?? "—"}</dd></div>
            <div><dt>Endpoint</dt><dd>{selectedProvider.endpoint}</dd></div>
            <div><dt>Runtime node</dt><dd>{selectedProvider.runtime_node || "—"}</dd></div>
          </dl>
          <StickyNote className="behavior-provider-caveat" variant="system" size="sm">
            {zh ? "API SUCCESS 只代表 Provider 成功返回；是否采用、发送或保持沉默，以 Smart Output validation 与 Runtime authority 为准。" : "API SUCCESS only means the provider returned successfully. Smart Output validation and Runtime authority decide whether it is accepted or delivered."}
          </StickyNote>
          <InspectorSection className="behavior-provider-json" title="Request summary" density="compact">
            <pre>{JSON.stringify(selectedProvider.request, null, 2)}</pre>
          </InspectorSection>
          <InspectorSection className="behavior-provider-json" title="Response summary" density="compact">
            <pre>{JSON.stringify(selectedProvider.response, null, 2)}</pre>
          </InspectorSection>
        </aside>
      )}

      {debugAccess === "allowed" && debugPanelOpen && (
        <aside className="behavior-debug-inspector" aria-label={zh ? "Discord Runtime 临时捕获" : "Discord Runtime ingress capture"}>
          <div className="behavior-debug-inspector-top">
            <div>
              <StickyLabel variant="warning">SUPER ADMIN · MEMORY ONLY</StickyLabel>
              <h3>{zh ? "Discord Runtime 临时捕获" : "Discord Runtime ingress capture"}</h3>
              <p>{zh ? "按 Server Profile 临时捕获发送到 Runtime 的 ingress payload。" : "Temporarily capture Runtime-bound ingress payloads for one server profile."}</p>
            </div>
            <IconButton type="button" onClick={() => { setDebugPanelOpen(false); setDebugRecordDetail(null); }} aria-label={zh ? "关闭临时捕获" : "Close Runtime capture"}>×</IconButton>
          </div>

          <Toast className="behavior-debug-warning" tone="warning" title={zh ? "仅用于短时调试" : "Short-lived debugging only"}>
            {zh
              ? "记录只保存在当前 Runtime 进程的内存里，进程重启即清空；只覆盖真正发送到 Runtime 的消息，不代表 Discord 收到的全部消息。"
              : "Records live only in this Runtime process's memory and are cleared by a restart. This covers only messages sent to Runtime, not every message Discord receives."}
          </Toast>

          <FormField
            className="behavior-debug-profile-field"
            label={zh ? "Server Profile" : "Server profile"}
            hint={zh ? "必须明确选择一个已有 Profile；不会自动选择。" : "Explicitly choose an existing profile; no profile is selected automatically."}
            htmlFor="behavior-debug-profile"
            required
          >
            <Select
              id="behavior-debug-profile"
              value={debugProfileId}
              disabled={debugProfilesLoading || debugWorking || debugSessionActive}
              onChange={(event) => setDebugProfileId(event.currentTarget.value)}
            >
              <option value="">{zh ? "选择 Server Profile…" : "Choose a server profile…"}</option>
              {debugProfiles.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.name}</option>
              ))}
            </Select>
          </FormField>

          {debugProfilesLoading && <Spinner label={zh ? "正在载入 Server Profiles" : "Loading server profiles"} />}
          {debugProfileError && <Toast tone="danger" title={zh ? "无法载入 Server Profiles" : "Could not load server profiles"}>{debugProfileError}</Toast>}

          {debugProfiles.length === 0 && !debugProfilesLoading && !debugProfileError && (
            <EmptyState
              className="behavior-debug-empty"
              title={zh ? "没有可选择的 Discord Server Profile。" : "No Discord server profiles are available."}
            />
          )}

          {selectedDebugProfile && (
            <div className="behavior-debug-profile-summary">
              <strong>{selectedDebugProfile.name}</strong>
              <span>{selectedDebugProfile.guild_name || selectedDebugProfile.guild_id || (zh ? "尚未连接 Guild" : "Guild not connected")}</span>
            </div>
          )}

          {!debugSessionActive && debugProfileId && !debugLoading && (
            <section className="behavior-debug-start" aria-labelledby="behavior-debug-ttl-title">
              <h4 id="behavior-debug-ttl-title">{zh ? "捕获时长" : "Capture duration"}</h4>
              <div className="behavior-debug-ttl" role="group" aria-label={zh ? "捕获时长" : "Capture duration"}>
                {DEBUG_TTL_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    variant={debugTtl === option.value ? "secondary" : "ghost"}
                    size="sm"
                    aria-pressed={debugTtl === option.value}
                    onClick={() => setDebugTtl(option.value)}
                  >
                    {zh ? option.zh : option.en}
                  </Button>
                ))}
              </div>
              <Button variant="primary" disabled={debugWorking} onClick={() => void startDebugSession()}>
                {debugWorking ? (zh ? "正在启动…" : "Starting…") : (zh ? "开始临时捕获" : "Start temporary capture")}
              </Button>
            </section>
          )}

          {debugLoading && <Spinner label={zh ? "正在载入捕获摘要" : "Loading capture summaries"} />}
          {debugError && <Toast tone="danger" title={zh ? "临时捕获操作失败" : "Runtime capture action failed"}>{debugError}</Toast>}

          {debugSession && (
            <>
              <section className="behavior-debug-session" aria-live="polite">
                <div className="behavior-debug-session-heading">
                  <div>
                    <small>{zh ? "捕获会话" : "Capture session"}</small>
                    <strong>{debugSession.guild_name || selectedDebugProfile?.name || shortId(debugSession.id)}</strong>
                  </div>
                  <StatusIndicator tone={statusTone(debugSession.status)}>{debugSession.status}</StatusIndicator>
                </div>
                <dl>
                  <div><dt>{zh ? "剩余时间" : "Time remaining"}</dt><dd>{debugSessionActive ? countdownLabel(debugSession.expires_at, debugNow, zh) : "—"}</dd></div>
                  <div><dt>{zh ? "记录" : "Records"}</dt><dd>{debugSession.record_count}</dd></div>
                  <div><dt>{zh ? "已淘汰" : "Evicted"}</dt><dd>{debugSession.evicted_record_count}</dd></div>
                  <div><dt>{zh ? "内存数据量" : "Captured bytes"}</dt><dd>{bytesLabel(debugSession.captured_bytes)}</dd></div>
                </dl>
                <small>{formatPortalTimestamp(debugSession.started_at, zh)} → {formatPortalTimestamp(debugSession.expires_at, zh)}</small>
                <div className="behavior-debug-session-actions">
                  <Button size="sm" variant="ghost" disabled={debugLoading || debugWorking} onClick={() => void refreshDebugRecords(debugSession.id)}>
                    {zh ? "刷新摘要" : "Refresh summaries"}
                  </Button>
                  {debugSessionActive && <Button size="sm" variant="danger" disabled={debugWorking} onClick={() => void stopDebugSession()}>{zh ? "停止捕获" : "Stop capture"}</Button>}
                  <Button size="sm" variant="danger" disabled={debugWorking || debugSession.record_count === 0} onClick={() => void clearDebugRecords()}>{zh ? "清除记录" : "Clear records"}</Button>
                </div>
              </section>

              <section className="behavior-debug-records" aria-labelledby="behavior-debug-records-title">
                <div className="behavior-debug-records-heading">
                  <h4 id="behavior-debug-records-title">{zh ? "记录摘要" : "Record summaries"}</h4>
                  <span>{debugRecordTotal}</span>
                </div>
                <p>{zh ? "这里只加载摘要；原始 payload 必须逐条明确 Reveal。" : "Only summaries load here. Each raw payload requires an explicit Reveal."}</p>
                <div className="behavior-debug-record-list">
                  {debugRecords.map((record) => (
                    <article key={record.id}>
                      <header>
                        <div><strong><code>{record.source_message_id || "—"}</code></strong><small>{formatPortalTimestamp(record.captured_at, zh)}</small></div>
                        <StatusIndicator tone={debugOutcomeTone(record.outcome)}>{debugOutcomeLabel(record.outcome, zh)}</StatusIndicator>
                      </header>
                      <dl>
                        <div><dt>{zh ? "字符" : "Chars"}</dt><dd>{record.character_count}</dd></div>
                        <div><dt>{zh ? "Payload" : "Payload"}</dt><dd>{bytesLabel(record.payload_bytes)}</dd></div>
                        <div><dt>Channel</dt><dd><code>{shortId(record.channel_id)}</code></dd></div>
                        <div><dt>Deployment</dt><dd><code>{shortId(record.deployment_id)}</code></dd></div>
                      </dl>
                      <Button size="sm" variant="ghost" disabled={debugWorking} onClick={() => void revealDebugRecord(record.id)}>
                        {zh ? "Reveal 原始 payload" : "Reveal raw payload"}
                      </Button>
                    </article>
                  ))}
                  {!debugLoading && debugRecords.length === 0 && (
                    <EmptyState className="behavior-debug-empty" title={zh ? "尚无捕获记录。" : "No capture records yet."} />
                  )}
                </div>
              </section>
            </>
          )}

          {debugRecordDetail && (
            <section className="behavior-debug-detail" aria-labelledby="behavior-debug-detail-title">
              <div className="behavior-debug-detail-heading">
                <div><small>{zh ? "敏感调试数据" : "Sensitive debug data"}</small><h4 id="behavior-debug-detail-title">{zh ? "已 Reveal 原始 payload" : "Raw payload revealed"}</h4></div>
                <IconButton type="button" onClick={() => setDebugRecordDetail(null)} aria-label={zh ? "隐藏原始 payload" : "Hide raw payload"}>×</IconButton>
              </div>
              <Toast tone="danger" title={zh ? "敏感内容正在显示" : "Sensitive content is visible"}>
                {zh ? "请勿复制到工单、Console 或持久化存储；完成调试后立即隐藏或清除记录。" : "Do not copy this into tickets, the console, or persistent storage. Hide or clear it as soon as debugging is complete."}
              </Toast>
              <pre>{JSON.stringify(debugRecordDetail.payload, null, 2)}</pre>
            </section>
          )}
        </aside>
      )}
    </div>
  );
}
