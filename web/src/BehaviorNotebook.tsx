import { useEffect, useMemo, useRef, useState } from "react";

import type { CharacterCard } from "./api";
import {
  deploymentApi,
  type DiscordConnectorLog
} from "./deploymentApi";
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
type TurnFilter = "all" | "selection" | "character";

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

interface CandidateDecision {
  deployment_id: string;
  character_card_id: string;
  character_name: string;
  participation_mode: string;
  selected: boolean;
  scored: boolean;
  score: number | null;
  minimum_score: number | null;
  eligible: boolean | null;
  semantic_relevance: number | null;
  signals: Record<string, number>;
  matched_topics: string[];
  matched_keywords: string[];
  matched_trigger_phrases: string[];
  matched_avoid_phrases: string[];
}

interface SemanticCandidate {
  deployment_id: string;
  semantic_relevance: number;
  profile_ready: boolean;
}

type NotebookEntry =
  | {
      kind: "selection";
      id: string;
      createdAt: string;
      log: DiscordConnectorLog;
    }
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

const SIGNAL_LABELS: Record<string, { en: string; zh: string }> = {
  question: { en: "Question", zh: "问题意图" },
  help_request: { en: "Help request", zh: "求助意图" },
  name_match: { en: "Name match", zh: "名字命中" },
  topic_match: { en: "Topic match", zh: "Topic 命中" },
  keyword_match: { en: "Keyword match", zh: "Keyword 命中" },
  trigger_phrase: { en: "Trigger phrase", zh: "触发短语" },
  semantic_match: { en: "E5 semantic", zh: "E5 语义" },
  initiative: { en: "Initiative", zh: "主动性" },
  short_message_penalty: { en: "Short-message penalty", zh: "短消息惩罚" },
  recent_turn_match: { en: "Recent-turn fit", zh: "近期回合匹配" },
  lightweight_follow_up: { en: "Light follow-up", zh: "轻量跟进" },
  cooldown_blocked: { en: "Cooldown block", zh: "Cooldown 阻断" },
  avoid_phrase_blocked: { en: "Avoid-phrase block", zh: "Avoid Phrase 阻断" },
  profile_disabled_blocked: { en: "Profile disabled", zh: "Profile 已关闭" }
};

function metadataRecord(values: Array<[string, string]>): Record<string, string> {
  return Object.fromEntries(values);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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

function candidateDecisions(log: DiscordConnectorLog): CandidateDecision[] {
  const raw = log.details.candidates;
  if (!Array.isArray(raw)) return [];
  return raw.map((value) => {
    const item = asRecord(value);
    const signalsRaw = asRecord(item.signals);
    const signals = Object.fromEntries(
      Object.entries(signalsRaw)
        .map(([key, signal]) => [key, asNumber(signal)])
        .filter((entry): entry is [string, number] => entry[1] !== null)
    );
    return {
      deployment_id: asString(item.deployment_id),
      character_card_id: asString(item.character_card_id),
      character_name: asString(item.character_name) || "Character",
      participation_mode: asString(item.participation_mode),
      selected: asBoolean(item.selected) ?? false,
      scored: asBoolean(item.scored) ?? false,
      score: asNumber(item.score),
      minimum_score: asNumber(item.minimum_score),
      eligible: asBoolean(item.eligible),
      semantic_relevance: asNumber(item.semantic_relevance),
      signals,
      matched_topics: asStrings(item.matched_topics),
      matched_keywords: asStrings(item.matched_keywords),
      matched_trigger_phrases: asStrings(item.matched_trigger_phrases),
      matched_avoid_phrases: asStrings(item.matched_avoid_phrases)
    };
  });
}

function semanticCandidates(log: DiscordConnectorLog | null): SemanticCandidate[] {
  if (!log || !Array.isArray(log.details.scores)) return [];
  return log.details.scores.map((value) => {
    const item = asRecord(value);
    return {
      deployment_id: asString(item.deployment_id),
      semantic_relevance: asNumber(item.semantic_relevance) ?? 0,
      profile_ready: asBoolean(item.profile_ready) ?? false
    };
  });
}

function selectionStatus(candidate: CandidateDecision): "selected" | "blocked" | "below" | "unscored" {
  if (candidate.selected) return "selected";
  if (!candidate.scored) return "unscored";
  if (candidate.eligible === false) return "blocked";
  return "below";
}

function signalLabel(key: string, zh: boolean): string {
  const label = SIGNAL_LABELS[key];
  return label ? (zh ? label.zh : label.en) : key.replaceAll("_", " ");
}

function signed(value: number): string {
  if (value > 0) return `+${value.toFixed(value % 1 ? 2 : 0)}`;
  return value.toFixed(value % 1 ? 2 : 0);
}

export function BehaviorNotebook({ cards }: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [runs, setRuns] = useState<RuntimeTraceSummary[]>([]);
  const [decisionLogs, setDecisionLogs] = useState<DiscordConnectorLog[]>([]);
  const [semanticLogs, setSemanticLogs] = useState<DiscordConnectorLog[]>([]);
  const [providerTraces, setProviderTraces] = useState<ProviderTraceSummary[]>([]);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RuntimeTraceView | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<ProviderTraceView | null>(null);
  const [tab, setTab] = useState<NotebookTab>("behavior");
  const [filter, setFilter] = useState<TurnFilter>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const entries = useMemo<NotebookEntry[]>(() => {
    const selectionEntries: NotebookEntry[] = decisionLogs.map((log) => ({
      kind: "selection",
      id: `selection:${log.id}`,
      createdAt: log.occurred_at,
      log
    }));
    const characterEntries: NotebookEntry[] = runs.map((run) => ({
      kind: "character",
      id: `character:${run.graph_run_id}`,
      createdAt: run.created_at,
      run
    }));
    return [...selectionEntries, ...characterEntries].sort(
      (left, right) => timestampMs(right.createdAt) - timestampMs(left.createdAt)
    );
  }, [decisionLogs, runs]);

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
      const [runtimePage, providerPage, decisions, semantics] = await Promise.all([
        runtimeTraceApi.list({ limit: 80, graphName: "character_turn", signal: controller.signal }),
        providerTraceApi.list({ limit: 100, signal: controller.signal }),
        deploymentApi.listDiscordLogs({ pageSize: 100, eventType: "smart_participation_decision" }),
        deploymentApi.listDiscordLogs({ pageSize: 100, eventType: "smart_participation_semantic_scored" })
      ]);
      if (controller.signal.aborted) return;
      setRuns(runtimePage.items);
      setProviderTraces(providerPage.items);
      setDecisionLogs(decisions.items);
      setSemanticLogs(semantics.items);
      const newestSelection = decisions.items[0];
      const newestRun = runtimePage.items[0];
      const nextId =
        newestSelection && (!newestRun || timestampMs(newestSelection.occurred_at) >= timestampMs(newestRun.created_at))
          ? `selection:${newestSelection.id}`
          : newestRun
            ? `character:${newestRun.graph_run_id}`
            : null;
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
      if (entry.kind === "selection") {
        const candidates = candidateDecisions(entry.log);
        return [
          asString(entry.log.details.trigger_preview),
          asString(entry.log.details.reason),
          ...candidates.map((candidate) => candidate.character_name)
        ]
          .join(" ")
          .toLowerCase()
          .includes(needle);
      }
      const card = cards.find((item) => item.id === entry.run.character_card_id);
      return [entry.run.graph_run_id, entry.run.operation_id, entry.run.deployment_id, card?.display_name ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [cards, entries, filter, query]);

  async function inspectProvider(traceId: string) {
    try {
      setSelectedProvider(await providerTraceApi.detail(traceId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function nearestSemanticLog(selection: DiscordConnectorLog): DiscordConnectorLog | null {
    const target = timestampMs(selection.occurred_at);
    const matched = semanticLogs
      .filter((log) => {
        if (selection.guild_id && log.guild_id && selection.guild_id !== log.guild_id) return false;
        if (selection.channel_id && log.channel_id && selection.channel_id !== log.channel_id) return false;
        return Math.abs(timestampMs(log.occurred_at) - target) <= 5_000;
      })
      .sort(
        (left, right) =>
          Math.abs(timestampMs(left.occurred_at) - target) -
          Math.abs(timestampMs(right.occurred_at) - target)
      );
    return matched[0] ?? null;
  }

  function renderSelectionTurn(log: DiscordConnectorLog) {
    const candidates = candidateDecisions(log);
    const semanticLog = nearestSemanticLog(log);
    const semantics = semanticCandidates(semanticLog);
    const reason = asString(log.details.reason) || "unknown";
    const selectedCount = asNumber(log.details.selected_count) ?? candidates.filter((candidate) => candidate.selected).length;
    const trigger = asString(log.details.trigger_preview);
    const semanticReason = semanticLog ? asString(semanticLog.details.reason) : "";
    const semanticModel = semanticLog ? asString(semanticLog.details.model) : "";
    const tieBreakUsed = semanticReason === "utility_tiebreak";
    const scoreScale = Math.max(
      1,
      ...candidates.flatMap((candidate) => [candidate.score ?? 0, candidate.minimum_score ?? 0])
    );

    return (
      <main className="behavior-notebook-page behavior-selection-page">
        <header className="behavior-notebook-header selection-header">
          <div className="behavior-selection-polaroid" aria-hidden="true">✦<span>WHO SPEAKS?</span></div>
          <div className="behavior-heading-copy">
            <span className="portal-v2-tape">SELECTION TURN NOTEBOOK</span>
            <h2>{selectedCount ? (zh ? `这一轮选中了 ${selectedCount} 个角色` : `${selectedCount} character(s) selected`) : (zh ? "这一轮没有角色被选中" : "No character was selected")}</h2>
            <p>Discord · {formatPortalTimestamp(log.occurred_at, zh)} · {candidates.length} {zh ? "个候选" : "candidates"}</p>
          </div>
          <div className={`behavior-completed-stamp ${selectedCount ? "stamp-completed" : "stamp-silent"}`}>
            {selectedCount ? "SELECTED" : "SILENT"}
          </div>
        </header>

        <div className="behavior-selection-body">
          <section className="behavior-trigger-note">
            <span>{zh ? "这一轮实际检查的消息" : "Trigger inspected this turn"}</span>
            <blockquote>{trigger || (zh ? "没有保存可读消息预览。" : "No readable trigger preview was persisted.")}</blockquote>
            <small>{zh ? `Selection reason · ${reason}` : `Selection reason · ${reason}`}</small>
          </section>

          <section className="behavior-judge-note">
            <header>
              <div>
                <span>{zh ? "选人前检查" : "PRE-SELECTION CHECKS"}</span>
                <strong>{semanticLog ? (zh ? "E5 语义评分已运行" : "E5 semantic scoring ran") : (zh ? "没有 E5 / Judge 事件" : "No E5 / Judge event")}</strong>
              </div>
              {tieBreakUsed && <em>UTILITY TIE-BREAK USED</em>}
            </header>
            {semanticLog ? (
              <>
                <p>
                  {zh
                    ? `模型 ${semanticModel || "semantic runtime"} · reason=${semanticReason || "ok"}。这里显示的是 Character Runtime 之前用来决定“谁有资格进入下一步”的检查。`
                    : `Model ${semanticModel || "semantic runtime"} · reason=${semanticReason || "ok"}. This happens before Character Runtime and helps decide who may continue.`}
                </p>
                <div className="behavior-semantic-score-list">
                  {semantics.map((semantic) => {
                    const candidate = candidates.find((item) => item.deployment_id === semantic.deployment_id);
                    return (
                      <div key={semantic.deployment_id}>
                        <span>{candidate?.character_name || shortId(semantic.deployment_id)}</span>
                        <strong>{semantic.profile_ready ? semantic.semantic_relevance.toFixed(3) : "not ready"}</strong>
                      </div>
                    );
                  })}
                </div>
                <small>
                  {zh
                    ? "Utility Participation Tie-break 只处理 E5 的灰区平手；它可以降低其他候选的语义支持，但不能把原本不合格的角色抬过参与阈值。"
                    : "Utility Participation Tie-break only resolves an E5 gray-zone tie. It may demote competing candidates, but cannot lift an ineligible character over the participation threshold."}
                </small>
              </>
            ) : (
              <p>{zh ? "这一轮可能在更早的 deterministic gate 就结束，或对应的 semantic event 已超出当前事件窗口。" : "This turn may have ended at an earlier deterministic gate, or its semantic event is outside the current event window."}</p>
            )}
          </section>

          <section className="behavior-candidate-board">
            <div className="behavior-section-title">
              <span className="behavior-doodle">✿</span>
              <h3>{zh ? "全部候选与得分权重" : "All candidates & score weights"}</h3>
            </div>
            <p className="behavior-candidate-guide">
              {zh
                ? "Score 是下方 signal 实际加减分的总和；Minimum 是该角色当前 style 的参与阈值。没有进入 Character Turn 的角色也会保留在这里。"
                : "Score is the sum of the signal contributions below; Minimum is that character's current participation threshold. Candidates that never enter Character Runtime remain visible here."}
            </p>
            <div className="behavior-candidate-grid">
              {candidates.map((candidate, index) => {
                const status = selectionStatus(candidate);
                const ratio = candidate.score === null ? 0 : Math.max(0, Math.min(1, candidate.score / scoreScale));
                const thresholdRatio = candidate.minimum_score === null ? 0 : Math.max(0, Math.min(1, candidate.minimum_score / scoreScale));
                const matches = [
                  ...candidate.matched_topics.map((value) => `topic · ${value}`),
                  ...candidate.matched_keywords.map((value) => `keyword · ${value}`),
                  ...candidate.matched_trigger_phrases.map((value) => `trigger · ${value}`),
                  ...candidate.matched_avoid_phrases.map((value) => `avoid · ${value}`)
                ];
                return (
                  <article className={`behavior-candidate-card candidate-${status}`} key={candidate.deployment_id || `${candidate.character_name}-${index}`}>
                    <header>
                      <div>
                        <small>#{index + 1} · {candidate.participation_mode || "smart"}</small>
                        <strong>{candidate.character_name}</strong>
                      </div>
                      <span>{status === "selected" ? (zh ? "已选中" : "SELECTED") : status === "blocked" ? (zh ? "被阻断" : "BLOCKED") : status === "below" ? (zh ? "未过线" : "BELOW") : (zh ? "未评分" : "NOT SCORED")}</span>
                    </header>
                    <div className="behavior-score-row">
                      <div><small>Score</small><strong>{candidate.score?.toFixed(3) ?? "—"}</strong></div>
                      <div><small>Minimum</small><strong>{candidate.minimum_score?.toFixed(3) ?? "—"}</strong></div>
                      <div><small>E5</small><strong>{candidate.semantic_relevance?.toFixed(3) ?? "—"}</strong></div>
                    </div>
                    <div className="behavior-score-rail" aria-label={zh ? "得分与阈值" : "Score and threshold"}>
                      <span className="behavior-score-fill" style={{ width: `${ratio * 100}%` }} />
                      {candidate.minimum_score !== null && <i style={{ left: `${thresholdRatio * 100}%` }} />}
                    </div>
                    <div className="behavior-signal-grid">
                      {Object.entries(candidate.signals).map(([key, value]) => (
                        <span className={value < 0 ? "is-negative" : value > 0 ? "is-positive" : "is-zero"} key={key}>
                          <small>{signalLabel(key, zh)}</small>
                          <b>{signed(value)}</b>
                        </span>
                      ))}
                    </div>
                    {matches.length > 0 && (
                      <div className="behavior-match-tags">
                        {matches.map((value) => <span key={value}>{value}</span>)}
                      </div>
                    )}
                  </article>
                );
              })}
              {candidates.length === 0 && <p className="behavior-empty">{zh ? "这轮没有 Smart Participation 候选。" : "No Smart Participation candidates were recorded."}</p>}
            </div>
          </section>

          <section className="behavior-selection-legend">
            <span>{zh ? "读法" : "How to read"}</span>
            <p>{zh ? "绿色卡 = 最终被选；粉色 = deterministic blocker；紫色 = 有评分但没达到选择条件；灰色 = 在评分前的全局 gate 就停止。" : "Mint = selected; rose = deterministic blocker; lavender = scored but not selected; gray = stopped at a global gate before candidate scoring."}</p>
          </section>
        </div>
      </main>
    );
  }

  function renderCharacterTurn() {
    if (selectedEntry?.kind !== "character") return null;
    if (!selectedRun) {
      return <main className="behavior-notebook-page"><div className="behavior-loading-note">{zh ? "正在翻开角色回合…" : "Opening Character Turn…"}</div></main>;
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
                  <div className="behavior-step-status"><span className={`behavior-status behavior-status-${step.status}`}>{step.status}</span><b>{durationLabel(step.durationMs)}</b></div>
                </header>
                {Object.keys(meta).length > 0 && <div className="behavior-meta-chips">{Object.entries(meta).slice(0, 8).map(([key, value]) => <span key={key}><small>{key}</small>{value || "—"}</span>)}</div>}
                {providers.map((provider, providerIndex) => (
                  <button type="button" className="behavior-provider-receipt" key={provider.trace_id} onClick={() => void inspectProvider(provider.trace_id)}>
                    <span>{step.nodeName === "turn_smart_output" ? (zh ? `格式修复 API #${providerIndex + 1}` : `Format-repair API #${providerIndex + 1}`) : `Provider API #${providerIndex + 1}`}</span>
                    <strong>{provider.response_model || provider.request_model || "Model call"}</strong>
                    <small>{durationLabel(provider.latency_ms)} · {provider.input_tokens ?? "—"} → {provider.output_tokens ?? "—"} tokens</small>
                    <em className={`behavior-status behavior-status-${provider.status}`}>{provider.status === "succeeded" ? "API SUCCESS" : provider.status}</em>
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
                {step.error && <p className="error-note">{step.error}</p>}
              </div>
            </article>
          );
        })}
        {steps.length > 0 && <div className="behavior-end-stamp">END OF TURN · ᓚᘏᗢ</div>}
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
            <nav className="behavior-tabs" aria-label={zh ? "观察视图" : "Observation view"}>
              {(["behavior", "flow", "state", "raw"] as NotebookTab[]).map((item) => <button type="button" key={item} className={tab === item ? "is-active" : ""} onClick={() => setTab(item)}>{item === "behavior" ? "✿ " : item === "flow" ? "↝ " : item === "state" ? "⇄ " : "▤ "}{item === "behavior" ? (zh ? "行为" : "Behavior") : item === "flow" ? "Flow" : item === "state" ? "State" : "Raw"}</button>)}
            </nav>
          </div>
          <div className={`behavior-completed-stamp stamp-${selectedRun.status}`}>{selectedRun.status}</div>
        </header>
        <div className="behavior-notebook-body">
          <div className="behavior-main-column">
            {tab === "behavior" && <><section className="behavior-summary-row"><article className="behavior-sticky behavior-sticky-yellow"><span>{zh ? "行为摘要" : "Behavior summary"} ✧</span><ul><li>{zh ? `执行了 ${steps.length} 个 Runtime 步骤。` : `${steps.length} Runtime steps were observed.`}</li><li>{zh ? `正式 Character generation ${modelSteps.length} 次。` : `${modelSteps.length} Character generation step(s).`}</li><li>{runProviders.filter((item) => item.runtime_node === "turn_smart_output").length ? (zh ? "Smart Output 曾触发格式修复 Provider call。" : "Smart Output invoked a format-repair provider call.") : (zh ? "没有额外格式修复模型调用。" : "No extra format-repair model call.")}</li><li>{zh ? `最终 Runtime authority = ${authorityMeta.action || selectedRun.status}。` : `Final Runtime authority = ${authorityMeta.action || selectedRun.status}.`}</li></ul></article><article className="behavior-sticky behavior-sticky-blue"><span>{zh ? "这一轮的证据" : "Evidence from this turn"}</span><div className="behavior-evidence-grid"><p><small>RAG</small><strong>{contextMeta.rag_pipeline || "—"}</strong></p><p><small>Provider API</small><strong>{runProviders.length}</strong></p><p><small>Tools</small><strong>{toolSteps.length}</strong></p><p><small>Outcome</small><strong>{authorityMeta.action || selectedRun.status}</strong></p></div></article></section>{renderFlow()}</>}
            {tab === "flow" && renderFlow()}
            {tab === "state" && <section className="behavior-state-board"><div className="behavior-section-title"><span className="behavior-doodle">⇄</span><h3>{zh ? "State 变化索引" : "State change index"}</h3></div>{steps.filter((step) => step.changedKeys.length).map((step) => <article key={step.key}><strong>{step.nodeName}</strong><div>{step.changedKeys.map((key) => <span key={key}>{key}</span>)}</div></article>)}</section>}
            {tab === "raw" && <section className="behavior-raw-sheet"><header><span>{zh ? "档案袋 / Raw Runtime Trace" : "Archive sheet / Raw Runtime Trace"}</span></header><pre>{JSON.stringify(selectedRun, null, 2)}</pre></section>}
          </div>
          <aside className="behavior-observation-margin">
            <section className="behavior-margin-card observation-card"><span className="behavior-margin-tab">Observation</span><dl><div><dt>{zh ? "模型步骤" : "Model steps"}</dt><dd>{modelSteps.length}</dd></div><div><dt>{zh ? "格式修复" : "Format repair"}</dt><dd>{runProviders.filter((item) => item.runtime_node === "turn_smart_output").length}</dd></div><div><dt>{zh ? "Provider API" : "Provider API"}</dt><dd>{runProviders.length}</dd></div><div><dt>{zh ? "总耗时" : "Total latency"}</dt><dd>{durationLabel(totalMs)}</dd></div></dl><div className="behavior-margin-pills"><span>RAG · {contextMeta.rag_pipeline || "—"}</span><span>Media · {mediaMeta.actual_perception || "—"}</span><span>Authority · {authorityMeta.action || selectedRun.status}</span></div></section>
            {runProviders.length > 0 && <section className="behavior-margin-card provider-card"><span className="behavior-margin-tab">Provider API</span>{runProviders.map((provider, index) => <button type="button" key={provider.trace_id} onClick={() => void inspectProvider(provider.trace_id)}><small>#{index + 1} · {provider.runtime_node || provider.category}</small><strong>{provider.response_model || provider.request_model}</strong><span>{provider.status === "succeeded" ? "API SUCCESS" : provider.status} · {durationLabel(provider.latency_ms)}</span></button>)}</section>}
            <section className="behavior-margin-card operation-card"><span className="behavior-margin-tab">Operation</span><p>{shortId(selectedRun.operation_id)}</p><small>{shortId(selectedRun.graph_run_id)}</small></section>
          </aside>
        </div>
      </main>
    );
  }

  return (
    <div className="behavior-notebook-shell">
      <aside className="behavior-run-sidebar">
        <div className="behavior-side-title"><span className="portal-v2-tape">ALL BEHAVIOR TURNS</span><button className="behavior-refresh" type="button" onClick={() => void loadRuns()} aria-label={zh ? "刷新" : "Refresh"}>↻</button></div>
        <div className="behavior-turn-filters">
          {(["all", "selection", "character"] as TurnFilter[]).map((value) => <button type="button" key={value} className={filter === value ? "is-active" : ""} onClick={() => setFilter(value)}>{value === "all" ? (zh ? "全部" : "All") : value === "selection" ? (zh ? "选人" : "Selection") : (zh ? "角色" : "Character")}</button>)}
        </div>
        <input className="behavior-run-search" value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder={zh ? "搜索角色、触发消息或 reason…" : "Search character, trigger, or reason…"} />
        <div className="behavior-run-list">
          {visibleEntries.map((entry) => {
            if (entry.kind === "selection") {
              const candidates = candidateDecisions(entry.log);
              const selectedNames = candidates.filter((item) => item.selected).map((item) => item.character_name);
              return <button type="button" key={entry.id} className={`behavior-selection-run ${selectedEntryId === entry.id ? "is-active" : ""}`} onClick={() => setSelectedEntryId(entry.id)}><span className="behavior-mini-avatar selection-avatar">✦</span><span className="behavior-run-copy"><strong>{selectedNames.length ? selectedNames.join(" · ") : (zh ? "无人入选" : "No selection")}</strong><small>{formatPortalTimestamp(entry.createdAt, zh)}</small><em>{zh ? `选人 · ${candidates.length} 候选` : `Selection · ${candidates.length} candidates`}</em></span><span className={`behavior-status ${selectedNames.length ? "behavior-status-completed" : "behavior-status-skipped"}`}>{selectedNames.length ? "selected" : "silent"}</span></button>;
            }
            const runCard = cards.find((item) => item.id === entry.run.character_card_id);
            return <button type="button" key={entry.id} className={selectedEntryId === entry.id ? "is-active" : ""} onClick={() => setSelectedEntryId(entry.id)}><span className={`behavior-mini-avatar portrait-${runCard?.portrait_variant ?? "lavender"}`}>{runCard?.display_name.slice(0, 1) || "C"}</span><span className="behavior-run-copy"><strong>{runCard?.display_name || (zh ? "角色回合" : "Character turn")}</strong><small>{formatPortalTimestamp(entry.createdAt, zh)}</small><em>{zh ? "角色 Runtime" : "Character Runtime"} · {entry.run.event_count} events</em></span><span className={`behavior-status behavior-status-${entry.run.status}`}>{entry.run.status}</span></button>;
          })}
          {!loading && visibleEntries.length === 0 && <p className="behavior-empty">{zh ? "还没有可观察的行为回合。" : "No observable behavior turns yet."}</p>}
        </div>
      </aside>

      {error && <p className="error-note behavior-page-error">{error}</p>}
      {!selectedEntry ? (
        <main className="behavior-notebook-page"><div className="behavior-loading-note">{loading ? (zh ? "正在翻开行为手帐…" : "Opening the behavior notebook…") : (zh ? "选择一个行为回合。" : "Select a behavior turn.")}</div></main>
      ) : selectedEntry.kind === "selection" ? renderSelectionTurn(selectedEntry.log) : renderCharacterTurn()}

      {selectedProvider && (
        <aside className="behavior-provider-inspector">
          <div className="behavior-provider-inspector-top"><div><span>PROVIDER API RECEIPT</span><h3>{selectedProvider.response_model || selectedProvider.request_model}</h3><p>{selectedProvider.runtime_node || selectedProvider.category} · {durationLabel(selectedProvider.latency_ms)}</p></div><button type="button" onClick={() => setSelectedProvider(null)}>×</button></div>
          <dl><div><dt>API status</dt><dd>{selectedProvider.status}</dd></div><div><dt>Tokens</dt><dd>{selectedProvider.input_tokens ?? "—"} → {selectedProvider.output_tokens ?? "—"}</dd></div><div><dt>Endpoint</dt><dd>{selectedProvider.endpoint}</dd></div><div><dt>Runtime node</dt><dd>{selectedProvider.runtime_node || "—"}</dd></div></dl>
          <p className="behavior-provider-caveat">{zh ? "API SUCCESS 只代表 Provider 成功返回；是否采用、发送或保持沉默，以 Smart Output validation 与 Runtime authority 为准。" : "API SUCCESS only means the provider returned successfully. Smart Output validation and Runtime authority decide whether it is accepted or delivered."}</p>
          <div className="behavior-provider-json"><span>Request summary</span><pre>{JSON.stringify(selectedProvider.request, null, 2)}</pre></div><div className="behavior-provider-json"><span>Response summary</span><pre>{JSON.stringify(selectedProvider.response, null, 2)}</pre></div>
        </aside>
      )}
    </div>
  );
}
