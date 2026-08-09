import { useEffect, useMemo, useState } from "react";

import {
  providerTraceApi,
  type ProviderTraceCategory,
  type ProviderTraceStatus,
  type ProviderTraceView
} from "./providerTraceApi";
import { useI18n } from "./i18n";

export function ProviderTraceAccessButton({ onOpen }: { onOpen: () => void }) {
  const { language } = useI18n();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let active = true;
    void providerTraceApi
      .list({ limit: 1 })
      .then(() => {
        if (active) setAllowed(true);
      })
      .catch(() => {
        if (active) setAllowed(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!allowed) return null;
  return (
    <button type="button" className="paper-button" onClick={onOpen}>
      {language === "zh-CN" ? "Provider Trace" : "Provider traces"}
    </button>
  );
}

function categoryLabel(category: ProviderTraceCategory, zh: boolean): string {
  if (category === "tool_calling") return zh ? "Tool Calling" : "Tool Calling";
  if (category === "character_turn") return zh ? "角色回合" : "Character Turn";
  return zh ? "模型调用" : "Model Call";
}

export function ProviderTraceViewer({
  onClose,
  embedded = false
}: {
  onClose: () => void;
  embedded?: boolean;
}) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [traces, setTraces] = useState<ProviderTraceView[]>([]);
  const [status, setStatus] = useState<ProviderTraceStatus | "all">("all");
  const [category, setCategory] = useState<ProviderTraceCategory | "all">("all");
  const [model, setModel] = useState("");
  const [appliedModel, setAppliedModel] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load(
    targetCursor: string | null = cursor,
    targetModel = appliedModel
  ) {
    try {
      setLoading(true);
      const next = await providerTraceApi.list({
        limit: 50,
        status,
        category,
        model: targetModel,
        cursor: targetCursor
      });
      setTraces(next.items);
      setNextCursor(next.next_cursor);
      setSelectedId((current) =>
        current && next.items.some((item) => item.trace_id === current)
          ? current
          : next.items[0]?.trace_id ?? null
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function resetAndLoad(targetModel = appliedModel) {
    setCursor(null);
    setCursorHistory([]);
    setPage(1);
    void load(null, targetModel);
  }

  function applyFilters() {
    const nextModel = model.trim();
    setAppliedModel(nextModel);
    resetAndLoad(nextModel);
  }

  function showOlder() {
    if (!nextCursor) return;
    setCursorHistory((current) => [...current, cursor]);
    setCursor(nextCursor);
    setPage((current) => current + 1);
    void load(nextCursor);
  }

  function showNewer() {
    const previous = cursorHistory.at(-1);
    if (previous === undefined) return;
    setCursorHistory((current) => current.slice(0, -1));
    setCursor(previous);
    setPage((current) => Math.max(1, current - 1));
    void load(previous);
  }

  useEffect(() => {
    resetAndLoad();
  }, [status, category]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(
      () => void load(cursor, appliedModel),
      5000
    );
    return () => window.clearInterval(timer);
  }, [autoRefresh, status, category, appliedModel, cursor]);

  const selected = useMemo(
    () => traces.find((item) => item.trace_id === selectedId) ?? null,
    [selectedId, traces]
  );

  async function clearAll() {
    const confirmed = window.confirm(
      zh
        ? "清除全部 Provider Trace？此操作无法撤销。"
        : "Clear every provider trace? This cannot be undone."
    );
    if (!confirmed) return;
    try {
      const result = await providerTraceApi.clear();
      setMessage(
        zh
          ? `已清除 ${result.deleted_count} 条 Trace。`
          : `Cleared ${result.deleted_count} traces.`
      );
      setTraces([]);
      setSelectedId(null);
      setCursor(null);
      setCursorHistory([]);
      setNextCursor(null);
      setPage(1);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <main className={`provider-trace-page${embedded ? " provider-trace-embedded" : ""}`}>
      <header className="provider-trace-header">
        <div>
          <p className="kicker">CHARACTER RELAY / SUPER ADMIN</p>
          <h1>{zh ? "Provider 请求与响应" : "Provider requests and responses"}</h1>
          <p>
            {zh
              ? "私密 Trace 只保存在 Character Relay 数据库。现在可按 Tool Calling、角色回合与普通模型调用分类筛选。API Key 与 Authorization Header 不会被保存。"
              : "Private traces stay in Character Relay. Filter them by Tool Calling, Character Turn, or general Model Call. API keys and Authorization headers are never stored."}
          </p>
        </div>
        <div className="provider-trace-header-actions">
          <button type="button" className="paper-button" onClick={() => void load(cursor)}>
            {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
          </button>
          <button type="button" className="paper-button danger-text" onClick={() => void clearAll()}>
            {zh ? "清除全部" : "Clear all"}
          </button>
          {!embedded && (
            <button type="button" className="ink-button" onClick={onClose}>
              {zh ? "返回 Portal" : "Back to Portal"}
            </button>
          )}
        </div>
      </header>

      <section className="paper-sheet provider-trace-controls">
        <label>
          {zh ? "类型" : "Category"}
          <select
            value={category}
            onChange={(event) =>
              setCategory(event.currentTarget.value as ProviderTraceCategory | "all")
            }
          >
            <option value="all">{zh ? "全部类型" : "All categories"}</option>
            <option value="tool_calling">Tool Calling</option>
            <option value="character_turn">{zh ? "角色回合" : "Character Turn"}</option>
            <option value="model_call">{zh ? "模型调用" : "Model Call"}</option>
          </select>
        </label>
        <label>
          {zh ? "状态" : "Status"}
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.currentTarget.value as ProviderTraceStatus | "all")
            }
          >
            <option value="all">{zh ? "全部" : "All"}</option>
            <option value="pending">Pending</option>
            <option value="succeeded">Succeeded</option>
            <option value="error">Error</option>
          </select>
        </label>
        <label>
          {zh ? "Model 搜索" : "Model search"}
          <input
            value={model}
            onChange={(event) => setModel(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyFilters();
            }}
            placeholder="deepseek-v4-flash"
          />
        </label>
        <button type="button" className="paper-button" onClick={applyFilters}>
          {zh ? "套用筛选" : "Apply filters"}
        </button>
        <label className="provider-trace-auto-refresh">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(event) => setAutoRefresh(event.currentTarget.checked)}
          />
          {zh ? "每 5 秒自动刷新" : "Refresh every 5 seconds"}
        </label>
        <span className="provider-trace-count">
          {zh ? `第 ${page} 页 · ${traces.length} 条` : `Page ${page} · ${traces.length} traces`}
        </span>
      </section>

      {error && <p className="error-note provider-trace-message">{error}</p>}
      {message && <p className="success-note provider-trace-message">{message}</p>}

      <section className="provider-trace-layout">
        <aside className="paper-sheet provider-trace-list">
          {loading && traces.length === 0 ? (
            <p>{zh ? "正在读取 Trace…" : "Loading traces…"}</p>
          ) : traces.length === 0 ? (
            <div className="provider-trace-empty">
              <strong>{zh ? "没有符合筛选的 Provider Trace" : "No matching provider traces"}</strong>
              <p>
                {zh
                  ? "下一次模型调用或 Tool Calling 后会出现在这里。"
                  : "The next model or Tool Calling request will appear here."}
              </p>
            </div>
          ) : (
            <>
              {traces.map((trace) => (
                <button
                  type="button"
                  key={trace.trace_id}
                  className={`provider-trace-list-item ${
                    selectedId === trace.trace_id ? "is-active" : ""
                  }`}
                  onClick={() => setSelectedId(trace.trace_id)}
                >
                  <div className="provider-trace-badge-row">
                    <span className={`provider-trace-category category-${trace.category}`}>
                      {categoryLabel(trace.category, zh)}
                    </span>
                    <span className={`provider-trace-status trace-${trace.status}`}>
                      {trace.status}
                    </span>
                  </div>
                  <strong>{trace.request_model || "unknown model"}</strong>
                  {trace.tool_names.length > 0 && (
                    <small className="provider-trace-tool-names">
                      {trace.tool_names.join(" · ")}
                    </small>
                  )}
                  <small>{new Date(trace.created_at).toLocaleString()}</small>
                  <small>
                    {trace.latency_ms ?? "—"} ms · {trace.input_tokens ?? "—"} /{" "}
                    {trace.output_tokens ?? "—"} tokens
                  </small>
                  <code>{trace.trace_id.slice(0, 12)}</code>
                </button>
              ))}
              <nav
                className="library-pagination"
                style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}
              >
                <button
                  type="button"
                  className="paper-button"
                  disabled={cursorHistory.length === 0 || loading}
                  onClick={showNewer}
                >
                  {zh ? "较新" : "Newer"}
                </button>
                <span>{page}</span>
                <button
                  type="button"
                  className="paper-button"
                  disabled={!nextCursor || loading}
                  onClick={showOlder}
                >
                  {zh ? "较旧" : "Older"}
                </button>
              </nav>
            </>
          )}
        </aside>

        <section className="paper-sheet provider-trace-detail">
          {!selected ? (
            <div className="provider-trace-empty">
              <strong>{zh ? "选择一条 Trace" : "Select a trace"}</strong>
            </div>
          ) : (
            <>
              <div className="provider-trace-detail-heading">
                <div>
                  <p className="tape-label">TRACE DETAIL</p>
                  <h2>{selected.request_model || "Provider call"}</h2>
                  <div className="provider-trace-badge-row">
                    <span className={`provider-trace-category category-${selected.category}`}>
                      {categoryLabel(selected.category, zh)}
                    </span>
                    {selected.tool_names.map((name) => (
                      <code key={name} className="provider-trace-tool-chip">{name}</code>
                    ))}
                  </div>
                  <code>{selected.trace_id}</code>
                </div>
                <span className={`provider-trace-status trace-${selected.status}`}>
                  {selected.status}
                </span>
              </div>

              <dl className="provider-trace-meta">
                <div><dt>Category</dt><dd>{categoryLabel(selected.category, zh)}</dd></div>
                <div><dt>Endpoint</dt><dd>{selected.endpoint}</dd></div>
                <div><dt>Trace mode</dt><dd>{selected.trace_mode}</dd></div>
                <div><dt>Status code</dt><dd>{selected.status_code ?? "—"}</dd></div>
                <div><dt>Latency</dt><dd>{selected.latency_ms ?? "—"} ms</dd></div>
                <div><dt>Input tokens</dt><dd>{selected.input_tokens ?? "—"}</dd></div>
                <div><dt>Output tokens</dt><dd>{selected.output_tokens ?? "—"}</dd></div>
                <div><dt>Response model</dt><dd>{selected.response_model || "—"}</dd></div>
                <div><dt>Created</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd></div>
              </dl>

              <TraceJson title={zh ? "发送给 Provider 的 Request" : "Request sent to provider"} value={selected.request} />
              {selected.retries.length > 0 && (
                <TraceJson title={zh ? "重试记录" : "Retries"} value={selected.retries} />
              )}
              {Object.keys(selected.response).length > 0 && (
                <TraceJson title={zh ? "Provider Response" : "Provider response"} value={selected.response} />
              )}
              {Object.keys(selected.error).length > 0 && (
                <TraceJson title={zh ? "Provider Error" : "Provider error"} value={selected.error} />
              )}
            </>
          )}
        </section>
      </section>
    </main>
  );
}

function TraceJson({ title, value }: { title: string; value: unknown }) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(value, null, 2);

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <section className="provider-trace-json-section">
      <div>
        <h3>{title}</h3>
        <button type="button" className="paper-button" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy JSON"}
        </button>
      </div>
      <pre><code>{text}</code></pre>
    </section>
  );
}
