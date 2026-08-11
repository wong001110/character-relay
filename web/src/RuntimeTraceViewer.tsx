import { useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "./i18n";
import { formatPortalTimestamp } from "./portalTime";
import {
  runtimeTraceApi,
  type RuntimeGraphName,
  type RuntimeTraceStatus,
  type RuntimeTraceSummary,
  type RuntimeTraceView
} from "./runtimeTraceApi";

function graphLabel(graph: RuntimeGraphName): string {
  if (graph === "condition_watch") return "Condition Watch";
  if (graph === "character_turn") return "Character Turn";
  return "Social Turn";
}

function nodeDescription(nodeName: string, zh: boolean): string {
  const descriptions: Record<string, [string, string]> = {
    turn_resolve: ["解析 Discord 消息、Deployment、Character Card 与 Target", "Resolve the Discord message, deployment, Character Card, and target"],
    turn_context: ["建立最近对话、RAG / Context 与 Smart Output 上下文", "Build recent conversation, RAG/context, and Smart Output context"],
    turn_model: ["执行角色模型回合；Media Context 会在模型调用前注入", "Run the Character model step; Media Context is injected immediately before the model call"],
    turn_tool: ["执行 Runtime 授权的 Tool Calling", "Execute Runtime-authorized Tool Calling"],
    turn_resolve_output: ["解析 / 修复 Smart Output", "Parse or repair Smart Output"],
    turn_authorize: ["Runtime 做最终权限与输出授权", "Apply final Runtime authorization"],
    turn_complete: ["结束当前 Character Turn", "Complete the Character Turn"],
    resolve: ["解析当前运行输入", "Resolve the current runtime input"],
    context: ["建立当前运行上下文", "Build runtime context"],
    model: ["调用模型", "Invoke the model"],
    tool: ["执行 Tool", "Execute a Tool"],
    output: ["整理输出", "Resolve output"],
    complete: ["完成运行", "Complete the run"]
  };
  const value = descriptions[nodeName];
  return value ? value[zh ? 0 : 1] : zh ? "Runtime 执行节点" : "Runtime execution node";
}

export function RuntimeTraceViewer({ onClose }: { onClose: () => void }) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [items, setItems] = useState<RuntimeTraceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<RuntimeTraceView | null>(null);
  const [graphName, setGraphName] = useState<RuntimeGraphName | "all">("all");
  const [status, setStatus] = useState<RuntimeTraceStatus | "all">("all");
  const [operationId, setOperationId] = useState("");
  const [appliedOperationId, setAppliedOperationId] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<string | null>>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);

  async function load(targetCursor: string | null = cursor, targetOperation = appliedOperationId) {
    listController.current?.abort();
    const controller = new AbortController();
    listController.current = controller;
    setLoading(true);
    try {
      const result = await runtimeTraceApi.list({
        limit: 50,
        graphName,
        status,
        operationId: targetOperation,
        cursor: targetCursor,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      setItems(result.items);
      setNextCursor(result.next_cursor);
      setSelectedId((current) =>
        current && result.items.some((item) => item.graph_run_id === current)
          ? current
          : result.items[0]?.graph_run_id ?? null
      );
      setError(null);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (listController.current === controller) {
        listController.current = null;
        setLoading(false);
      }
    }
  }

  function resetAndLoad(targetOperation = appliedOperationId) {
    setCursor(null);
    setHistory([]);
    setNextCursor(null);
    setPage(1);
    void load(null, targetOperation);
  }

  useEffect(() => {
    resetAndLoad();
  }, [graphName, status]);

  useEffect(() => {
    detailController.current?.abort();
    setSelected(null);
    if (!selectedId) return;
    const controller = new AbortController();
    detailController.current = controller;
    void runtimeTraceApi
      .detail(selectedId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setSelected(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => controller.abort();
  }, [selectedId]);

  useEffect(
    () => () => {
      listController.current?.abort();
      detailController.current?.abort();
    },
    []
  );

  const selectedSummary = useMemo(
    () => items.find((item) => item.graph_run_id === selectedId) ?? null,
    [items, selectedId]
  );

  function applyOperationFilter() {
    const value = operationId.trim();
    setAppliedOperationId(value);
    resetAndLoad(value);
  }

  async function clearAll() {
    const confirmed = window.confirm(
      zh
        ? "清除全部 Runtime Trace？此操作不会删除业务状态，但无法撤销。"
        : "Clear all Runtime Traces? Business state is preserved, but this cannot be undone."
    );
    if (!confirmed) return;
    try {
      await runtimeTraceApi.clear();
      setItems([]);
      setSelectedId(null);
      setSelected(null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <main className="provider-trace-page provider-trace-embedded">
      <header className="provider-trace-header">
        <div>
          <p className="kicker">LANGGRAPH / DURABLE RUNTIME</p>
          <h1>Runtime Trace Explorer</h1>
          <p>
            {zh
              ? "把这里当成一轮 Character Relay 执行的 Timeline：从解析消息、建立 Context、执行模型 / Tool，到授权输出。它回答的是“这一轮按什么顺序走过哪些 Runtime 节点”。Provider Trace 则回答“其中实际向哪些外部模型发了请求”。因此一条 Runtime Trace 可以对应多条 Provider Trace。"
              : "Treat this as the timeline for one Character Relay execution: message resolution, context building, model/Tool execution, and output authorization. It answers which Runtime nodes ran and in what order. Provider Trace answers which external model requests were actually made inside that run, so one Runtime Trace can correspond to multiple Provider Traces."}
          </p>
          <p>
            {zh
              ? "为了隐私与稳定性，这里只保存节点状态与有限 metadata，不保存完整 Prompt、RAG 原文、Credential、Tool 参数或 Tool Result。Media Understanding 的实际 Vision request/response 请到 Provider Trace → 媒体理解查看；如果命中 Media cache，则不会产生新的 Provider Trace。"
              : "For privacy and durability this stores only node state and bounded metadata, not full prompts, RAG text, credentials, Tool arguments, or Tool results. Inspect Provider Trace → Media Understanding for the actual Vision request/response. A Media cache hit does not create a new Provider Trace."}
          </p>
        </div>
        <div className="provider-trace-header-actions">
          <button type="button" className="paper-button" onClick={() => void load(cursor)}>
            {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
          </button>
          <button type="button" className="paper-button danger-text" onClick={() => void clearAll()}>
            {zh ? "清除 Trace" : "Clear traces"}
          </button>
          <button type="button" className="ink-button" onClick={onClose}>
            {zh ? "返回工具箱" : "Back to toolbox"}
          </button>
        </div>
      </header>

      <section className="paper-sheet provider-trace-controls">
        <label>
          Graph
          <select
            value={graphName}
            onChange={(event) => setGraphName(event.currentTarget.value as RuntimeGraphName | "all")}
          >
            <option value="all">{zh ? "全部 Graph" : "All graphs"}</option>
            <option value="condition_watch">Condition Watch</option>
            <option value="character_turn">Character Turn</option>
            <option value="social_turn">Social Turn</option>
          </select>
        </label>
        <label>
          {zh ? "状态" : "Status"}
          <select
            value={status}
            onChange={(event) => setStatus(event.currentTarget.value as RuntimeTraceStatus | "all")}
          >
            <option value="all">{zh ? "全部" : "All"}</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label>
          operation_id
          <input
            value={operationId}
            onChange={(event) => setOperationId(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyOperationFilter();
            }}
            placeholder="durable operation id"
          />
        </label>
        <button type="button" className="paper-button" onClick={applyOperationFilter}>
          {zh ? "套用" : "Apply"}
        </button>
        <span className="provider-trace-count">
          {zh ? `第 ${page} 页 · ${items.length} 条` : `Page ${page} · ${items.length} runs`}
        </span>
      </section>

      {error && <p className="error-note provider-trace-message">{error}</p>}

      <section className="provider-trace-layout">
        <aside className="paper-sheet provider-trace-list">
          {loading && items.length === 0 ? (
            <p>{zh ? "正在读取 Runtime Trace…" : "Loading Runtime Traces…"}</p>
          ) : items.length === 0 ? (
            <div className="provider-trace-empty">
              <strong>{zh ? "目前没有符合条件的 Runtime Trace" : "No matching Runtime Traces"}</strong>
            </div>
          ) : (
            items.map((item) => (
              <button
                type="button"
                key={item.graph_run_id}
                className={`provider-trace-list-item ${selectedId === item.graph_run_id ? "is-active" : ""}`}
                onClick={() => setSelectedId(item.graph_run_id)}
              >
                <div className="provider-trace-badge-row">
                  <span className="provider-trace-category">{graphLabel(item.graph_name)}</span>
                  <span className={`provider-trace-status trace-${item.status}`}>
                    {item.status}
                  </span>
                </div>
                <strong>{item.last_node || item.graph_name}</strong>
                <small>{item.operation_id ? `op · ${item.operation_id.slice(0, 12)}` : "no operation id"}</small>
                <small>{item.deployment_id ? `deployment · ${item.deployment_id.slice(0, 12)}` : "—"}</small>
                <small>{item.event_count} events · {formatPortalTimestamp(item.created_at, zh)}</small>
              </button>
            ))
          )}
          <div className="provider-trace-pagination">
            <button
              type="button"
              className="paper-button"
              disabled={history.length === 0}
              onClick={() => {
                const previous = history.at(-1);
                if (previous === undefined) return;
                setHistory((current) => current.slice(0, -1));
                setCursor(previous);
                setPage((current) => Math.max(1, current - 1));
                void load(previous);
              }}
            >
              {zh ? "较新" : "Newer"}
            </button>
            <button
              type="button"
              className="paper-button"
              disabled={!nextCursor}
              onClick={() => {
                if (!nextCursor) return;
                setHistory((current) => [...current, cursor]);
                setCursor(nextCursor);
                setPage((current) => current + 1);
                void load(nextCursor);
              }}
            >
              {zh ? "较旧" : "Older"}
            </button>
          </div>
        </aside>

        <article className="paper-sheet provider-trace-detail">
          {!selectedSummary ? (
            <p>{zh ? "选择一个 Graph Run 查看执行 Timeline。" : "Select a graph run to inspect its execution timeline."}</p>
          ) : !selected ? (
            <p>{zh ? "正在读取节点 Timeline…" : "Loading node timeline…"}</p>
          ) : (
            <>
              <div className="provider-trace-detail-heading">
                <div>
                  <p className="kicker">{graphLabel(selected.graph_name)}</p>
                  <h2>{selected.graph_run_id}</h2>
                </div>
                <span className={`provider-trace-status trace-${selected.status}`}>
                  {selected.status}
                </span>
              </div>
              <dl className="provider-trace-meta-grid">
                <div><dt>operation_id</dt><dd>{selected.operation_id || "—"}</dd></div>
                <div><dt>deployment</dt><dd>{selected.deployment_id || "—"}</dd></div>
                <div><dt>character_card</dt><dd>{selected.character_card_id || "—"}</dd></div>
                <div><dt>{zh ? "Timeline 事件" : "Timeline events"}</dt><dd>{selected.event_count}</dd></div>
              </dl>
              <div className="provider-trace-json-stack">
                {selected.events.map((event, index) => (
                  <section key={event.id} className="provider-trace-json-card">
                    <div className="provider-trace-badge-row">
                      <strong>#{index + 1} · {event.node_name}</strong>
                      <span className={`provider-trace-status trace-${event.status}`}>{event.status}</span>
                    </div>
                    <p>{nodeDescription(event.node_name, zh)}</p>
                    <small>{event.node_kind} · {formatPortalTimestamp(event.created_at, zh)}</small>
                    {event.changed_keys.length > 0 && (
                      <p>{zh ? "State changed" : "State changed"}: {event.changed_keys.join(" · ")}</p>
                    )}
                    {event.metadata.length > 0 && (
                      <p>{event.metadata.map(([key, value]) => `${key}=${value}`).join(" · ")}</p>
                    )}
                    {event.error && <p className="error-note">{event.error}</p>}
                  </section>
                ))}
              </div>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
