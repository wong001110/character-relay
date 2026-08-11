import { useEffect, useMemo, useRef, useState } from "react";

import type { CharacterCard } from "./api";
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
import { useI18n } from "./i18n";

type NotebookTab = "behavior" | "flow" | "state" | "raw";

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

const NODE_COPY: Record<string, { en: string; zh: string; icon: string }> = {
  turn_resolve: { en: "Resolve target", zh: "解析目标", icon: "◎" },
  turn_context: { en: "Build context", zh: "建立上下文", icon: "▤" },
  turn_model: { en: "Character reasoning", zh: "角色推理", icon: "✦" },
  turn_tool_execution: { en: "Tool execution", zh: "工具执行", icon: "⚒" },
  turn_media_epistemic: { en: "Media note", zh: "媒体观察", icon: "◉" },
  turn_smart_output: { en: "Smart output", zh: "输出决策", icon: "✧" },
  turn_authority: { en: "Runtime authority", zh: "Runtime 授权", icon: "♢" }
};

function metadataRecord(values: Array<[string, string]>): Record<string, string> {
  return Object.fromEntries(values);
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
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

function durationLabel(value: number | null): string {
  if (value === null) return "…";
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)}s`;
  return `${value}ms`;
}

function shortId(value: string): string {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

export function BehaviorNotebook({ cards }: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [runs, setRuns] = useState<RuntimeTraceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<RuntimeTraceView | null>(null);
  const [providerTraces, setProviderTraces] = useState<ProviderTraceSummary[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<ProviderTraceView | null>(null);
  const [tab, setTab] = useState<NotebookTab>("behavior");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const runController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);

  async function loadRuns() {
    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    setLoading(true);
    try {
      const [runtimePage, providerPage] = await Promise.all([
        runtimeTraceApi.list({ limit: 80, graphName: "character_turn", signal: controller.signal }),
        providerTraceApi.list({ limit: 100, signal: controller.signal })
      ]);
      if (controller.signal.aborted) return;
      setRuns(runtimePage.items);
      setProviderTraces(providerPage.items);
      setSelectedId((current) =>
        current && runtimePage.items.some((item) => item.graph_run_id === current)
          ? current
          : runtimePage.items[0]?.graph_run_id ?? null
      );
      setError(null);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (runController.current === controller) {
        runController.current = null;
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadRuns();
    return () => runController.current?.abort();
  }, []);

  useEffect(() => {
    detailController.current?.abort();
    setSelected(null);
    setSelectedProvider(null);
    if (!selectedId) return;
    const controller = new AbortController();
    detailController.current = controller;
    void runtimeTraceApi
      .detail(selectedId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSelected(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => controller.abort();
  }, [selectedId]);

  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return runs;
    return runs.filter((run) => {
      const card = cards.find((item) => item.id === run.character_card_id);
      return [run.graph_run_id, run.operation_id, run.deployment_id, card?.display_name ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [cards, query, runs]);

  const steps = useMemo(() => projectSteps(selected?.events ?? []), [selected]);
  const card = selected
    ? cards.find((item) => item.id === selected.character_card_id) ?? null
    : null;
  const runProviders = useMemo(
    () =>
      selected
        ? providerTraces.filter((item) => item.graph_run_id === selected.graph_run_id)
        : [],
    [providerTraces, selected]
  );
  const runStart = steps[0]?.startedAt ?? selected?.created_at ?? "";
  const runEnd = [...steps].reverse().find((step) => step.completedAt)?.completedAt ?? selected?.updated_at ?? "";
  const totalMs = runStart && runEnd ? Math.max(0, timestampMs(runEnd) - timestampMs(runStart)) : null;
  const modelSteps = steps.filter((step) => step.nodeName === "turn_model" && step.status === "completed");
  const toolSteps = steps.filter((step) => step.nodeName === "turn_tool_execution" && step.status === "completed");
  const contextMeta = metadataRecord(
    steps.find((step) => step.nodeName === "turn_context")?.metadata ?? []
  );
  const authorityMeta = metadataRecord(
    [...steps].reverse().find((step) => step.nodeName === "turn_authority")?.metadata ?? []
  );
  const mediaMeta = metadataRecord(
    [...steps].reverse().find((step) => step.nodeName === "turn_media_epistemic")?.metadata ?? []
  );

  async function inspectProvider(traceId: string) {
    try {
      setSelectedProvider(await providerTraceApi.detail(traceId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function stepProvider(step: ProjectedStep): ProviderTraceSummary[] {
    return runProviders.filter((item) => item.runtime_node === step.nodeName);
  }

  function renderFlow() {
    return (
      <section className="behavior-flow-stack">
        <div className="behavior-section-title">
          <span className="behavior-doodle" aria-hidden="true">✿</span>
          <h3>{zh ? "执行流程" : "Execution flow"}</h3>
        </div>
        {steps.map((step, index) => {
          const copy = NODE_COPY[step.nodeName] ?? {
            en: step.nodeName,
            zh: step.nodeName,
            icon: "○"
          };
          const meta = metadataRecord(step.metadata);
          const providers = stepProvider(step);
          return (
            <article className={`behavior-step behavior-kind-${step.nodeKind}`} key={step.key}>
              <div className="behavior-step-number">{index + 1}</div>
              <div className="behavior-step-card">
                <header>
                  <div>
                    <span className="behavior-step-icon" aria-hidden="true">{copy.icon}</span>
                    <strong>{step.nodeName}</strong>
                    <small>{zh ? copy.zh : copy.en}</small>
                  </div>
                  <div className="behavior-step-status">
                    <span className={`behavior-status behavior-status-${step.status}`}>{step.status}</span>
                    <b>{durationLabel(step.durationMs)}</b>
                  </div>
                </header>

                {Object.keys(meta).length > 0 && (
                  <div className="behavior-meta-chips">
                    {Object.entries(meta).slice(0, 6).map(([key, value]) => (
                      <span key={key}><small>{key}</small>{value || "—"}</span>
                    ))}
                  </div>
                )}

                {providers.map((provider, providerIndex) => (
                  <button
                    type="button"
                    className="behavior-provider-receipt"
                    key={provider.trace_id}
                    onClick={() => void inspectProvider(provider.trace_id)}
                  >
                    <span>Provider Call #{providerIndex + 1}</span>
                    <strong>{provider.response_model || provider.request_model || "Model call"}</strong>
                    <small>
                      {durationLabel(provider.latency_ms)} · {provider.input_tokens ?? "—"} → {provider.output_tokens ?? "—"} tokens
                    </small>
                    <em className={`behavior-status behavior-status-${provider.status}`}>{provider.status}</em>
                  </button>
                ))}

                {step.nodeName === "turn_tool_execution" && (
                  <div className="behavior-tool-ticket">
                    <span>{zh ? "工具票据" : "Tool ticket"}</span>
                    <strong>{meta.executed_count ?? "0"} {zh ? "个工具已执行" : "tool(s) executed"}</strong>
                    <small>{zh ? `结果 ${meta.tool_result_count ?? "0"}` : `${meta.tool_result_count ?? "0"} result(s)`}</small>
                  </div>
                )}

                {step.nodeName === "turn_media_epistemic" && (
                  <div className="behavior-media-note">
                    <span>{zh ? "媒体便签" : "Media note"}</span>
                    <strong>{meta.actual_perception || "—"}</strong>
                    <small>{meta.response_stance ? `${zh ? "姿态" : "stance"}: ${meta.response_stance}` : ""}</small>
                    {meta.media_cache_hits && <em>Cache · {meta.media_cache_hits}</em>}
                  </div>
                )}

                {step.error && <p className="error-note">{step.error}</p>}
              </div>
            </article>
          );
        })}
        {steps.length > 0 && <div className="behavior-end-stamp">END OF TURN · ᓚᘏᗢ</div>}
      </section>
    );
  }

  return (
    <div className="behavior-notebook-shell">
      <aside className="behavior-run-sidebar">
        <div className="behavior-side-title">
          <span className="portal-v2-tape">RECENT TURNS</span>
          <button className="behavior-refresh" type="button" onClick={() => void loadRuns()} aria-label={zh ? "刷新" : "Refresh"}>↻</button>
        </div>
        <input
          className="behavior-run-search"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          placeholder={zh ? "搜索角色或 operation…" : "Search character or operation…"}
        />
        <div className="behavior-run-list">
          {filteredRuns.map((run) => {
            const runCard = cards.find((item) => item.id === run.character_card_id);
            return (
              <button
                type="button"
                key={run.graph_run_id}
                className={selectedId === run.graph_run_id ? "is-active" : ""}
                onClick={() => setSelectedId(run.graph_run_id)}
              >
                <span className={`behavior-mini-avatar portrait-${runCard?.portrait_variant ?? "lavender"}`}>
                  {runCard?.display_name.slice(0, 1) || "C"}
                </span>
                <span className="behavior-run-copy">
                  <strong>{runCard?.display_name || (zh ? "角色回合" : "Character turn")}</strong>
                  <small>{formatPortalTimestamp(run.created_at, zh)}</small>
                  <em>{shortId(run.operation_id)} · {run.event_count} events</em>
                </span>
                <span className={`behavior-status behavior-status-${run.status}`}>{run.status}</span>
              </button>
            );
          })}
          {!loading && filteredRuns.length === 0 && (
            <p className="behavior-empty">{zh ? "还没有 Character Turn。" : "No Character Turns yet."}</p>
          )}
        </div>
      </aside>

      <main className="behavior-notebook-page">
        {error && <p className="error-note behavior-page-error">{error}</p>}
        {!selected ? (
          <div className="behavior-loading-note">
            {loading ? (zh ? "正在翻开行为手帐…" : "Opening the behavior notebook…") : zh ? "选择一个角色回合。" : "Select a Character Turn."}
          </div>
        ) : (
          <>
            <header className="behavior-notebook-header">
              <div className={`behavior-polaroid portrait-${card?.portrait_variant ?? "lavender"}`}>
                <div className="behavior-polaroid-photo">
                  <img src="/assets/character-silhouette.svg" alt="" />
                </div>
                <span>{card?.display_name || "Character"} ♡</span>
              </div>
              <div className="behavior-heading-copy">
                <span className="portal-v2-tape">CHARACTER TURN NOTEBOOK</span>
                <h2>{card ? `${card.display_name} ${zh ? "完成了一次角色回合" : "completed a character turn"}` : zh ? "角色回合" : "Character turn"}</h2>
                <p>Discord · {formatPortalTimestamp(selected.created_at, zh)} → {formatPortalTimestamp(selected.updated_at, zh)} · {durationLabel(totalMs)}</p>
                <nav className="behavior-tabs" aria-label={zh ? "观察视图" : "Observation view"}>
                  {(["behavior", "flow", "state", "raw"] as NotebookTab[]).map((item) => (
                    <button
                      type="button"
                      key={item}
                      className={tab === item ? "is-active" : ""}
                      onClick={() => setTab(item)}
                    >
                      {item === "behavior" ? "✿ " : item === "flow" ? "↝ " : item === "state" ? "⇄ " : "▤ "}
                      {item === "behavior" ? (zh ? "行为" : "Behavior") : item === "flow" ? "Flow" : item === "state" ? "State" : "Raw"}
                    </button>
                  ))}
                </nav>
              </div>
              <div className={`behavior-completed-stamp stamp-${selected.status}`}>{selected.status}</div>
            </header>

            <div className="behavior-notebook-body">
              <div className="behavior-main-column">
                {tab === "behavior" && (
                  <>
                    <section className="behavior-summary-row">
                      <article className="behavior-sticky behavior-sticky-yellow">
                        <span>{zh ? "行为摘要" : "Behavior summary"} ✧</span>
                        <ul>
                          <li>{zh ? `执行了 ${steps.length} 个 Runtime 步骤。` : `${steps.length} Runtime steps were observed.`}</li>
                          <li>{zh ? `角色模型执行 ${modelSteps.length} 次。` : `${modelSteps.length} character model step(s) ran.`}</li>
                          <li>{toolSteps.length ? (zh ? `工具流程执行 ${toolSteps.length} 次。` : `${toolSteps.length} tool execution step(s) ran.`) : (zh ? "这一轮没有 Runtime Tool。" : "No Runtime Tool was executed in this turn.")}</li>
                          <li>{authorityMeta.action ? (zh ? `最终由 Runtime 授权为 ${authorityMeta.action}。` : `Runtime finalized the turn as ${authorityMeta.action}.`) : (zh ? "最终状态来自 Runtime Trace。" : "Final state is grounded in Runtime Trace.")}</li>
                        </ul>
                      </article>
                      <article className="behavior-sticky behavior-sticky-blue">
                        <span>{zh ? "这一轮的证据" : "Evidence from this turn"}</span>
                        <div className="behavior-evidence-grid">
                          <p><small>RAG</small><strong>{contextMeta.rag_pipeline || "—"}</strong></p>
                          <p><small>Provider</small><strong>{runProviders.length}</strong></p>
                          <p><small>Tools</small><strong>{toolSteps.length}</strong></p>
                          <p><small>Outcome</small><strong>{authorityMeta.action || selected.status}</strong></p>
                        </div>
                      </article>
                    </section>
                    {renderFlow()}
                  </>
                )}

                {tab === "flow" && renderFlow()}

                {tab === "state" && (
                  <section className="behavior-state-board">
                    <div className="behavior-section-title"><span className="behavior-doodle">⇄</span><h3>{zh ? "State 变化索引" : "State change index"}</h3></div>
                    <p className="behavior-state-guide">{zh ? "当前 Runtime Trace 只持久化 privacy-safe changed keys；值级 before → after 会在后续 trace contract 扩展后显示。" : "The current Runtime Trace persists privacy-safe changed keys. Value-level before → after will appear when the trace contract is expanded."}</p>
                    {steps.filter((step) => step.changedKeys.length).map((step) => (
                      <article key={step.key}>
                        <strong>{step.nodeName}</strong>
                        <div>{step.changedKeys.map((key) => <span key={key}>{key}</span>)}</div>
                      </article>
                    ))}
                  </section>
                )}

                {tab === "raw" && (
                  <section className="behavior-raw-sheet">
                    <header><span>{zh ? "档案袋 / Raw Runtime Trace" : "Archive sheet / Raw Runtime Trace"}</span></header>
                    <pre>{JSON.stringify(selected, null, 2)}</pre>
                  </section>
                )}
              </div>

              <aside className="behavior-observation-margin">
                <section className="behavior-margin-card observation-card">
                  <span className="behavior-margin-tab">Observation</span>
                  <dl>
                    <div><dt>{zh ? "模型步骤" : "Model steps"}</dt><dd>{modelSteps.length}</dd></div>
                    <div><dt>{zh ? "工具步骤" : "Tool steps"}</dt><dd>{toolSteps.length}</dd></div>
                    <div><dt>{zh ? "Provider 调用" : "Provider calls"}</dt><dd>{runProviders.length}</dd></div>
                    <div><dt>{zh ? "总耗时" : "Total latency"}</dt><dd>{durationLabel(totalMs)}</dd></div>
                  </dl>
                  <div className="behavior-margin-pills">
                    <span>RAG · {contextMeta.rag_pipeline || "—"}</span>
                    <span>Media · {mediaMeta.actual_perception || "—"}</span>
                    <span>Outcome · {authorityMeta.action || selected.status}</span>
                  </div>
                </section>

                {runProviders.length > 0 && (
                  <section className="behavior-margin-card provider-card">
                    <span className="behavior-margin-tab">Provider Calls</span>
                    {runProviders.map((provider, index) => (
                      <button type="button" key={provider.trace_id} onClick={() => void inspectProvider(provider.trace_id)}>
                        <small>#{index + 1} · {provider.runtime_node || provider.category}</small>
                        <strong>{provider.response_model || provider.request_model}</strong>
                        <span>{durationLabel(provider.latency_ms)} · {provider.input_tokens ?? "—"} → {provider.output_tokens ?? "—"}</span>
                      </button>
                    ))}
                  </section>
                )}

                {mediaMeta.actual_perception && (
                  <section className="behavior-margin-card media-card">
                    <span className="behavior-margin-tab">Media behavior</span>
                    <strong>{mediaMeta.actual_perception}</strong>
                    <p>{mediaMeta.response_stance ? `${zh ? "社交姿态" : "Social stance"}: ${mediaMeta.response_stance}` : ""}</p>
                    {mediaMeta.attention_reason && <small>{mediaMeta.attention_reason}</small>}
                  </section>
                )}

                <section className="behavior-margin-card operation-card">
                  <span className="behavior-margin-tab">Operation</span>
                  <p>{shortId(selected.operation_id)}</p>
                  <small>{shortId(selected.graph_run_id)}</small>
                </section>
              </aside>
            </div>
          </>
        )}
      </main>

      {selectedProvider && (
        <aside className="behavior-provider-inspector">
          <div className="behavior-provider-inspector-top">
            <div>
              <span>PROVIDER RECEIPT</span>
              <h3>{selectedProvider.response_model || selectedProvider.request_model}</h3>
              <p>{selectedProvider.runtime_node || selectedProvider.category} · {durationLabel(selectedProvider.latency_ms)}</p>
            </div>
            <button type="button" onClick={() => setSelectedProvider(null)}>×</button>
          </div>
          <dl>
            <div><dt>Status</dt><dd>{selectedProvider.status}</dd></div>
            <div><dt>Tokens</dt><dd>{selectedProvider.input_tokens ?? "—"} → {selectedProvider.output_tokens ?? "—"}</dd></div>
            <div><dt>Endpoint</dt><dd>{selectedProvider.endpoint}</dd></div>
            <div><dt>Trace</dt><dd>{shortId(selectedProvider.trace_id)}</dd></div>
          </dl>
          <section>
            <span>{zh ? "请求摘要" : "Request summary"}</span>
            <pre>{JSON.stringify(selectedProvider.request, null, 2)}</pre>
          </section>
          <section>
            <span>{zh ? "响应摘要" : "Response summary"}</span>
            <pre>{JSON.stringify(selectedProvider.response, null, 2)}</pre>
          </section>
        </aside>
      )}
    </div>
  );
}
