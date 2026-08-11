import { useEffect, useMemo, useRef, useState } from "react";

import { api, type AdminAccount } from "./api";
import {
  providerTraceApi,
  type ProviderTraceCategory,
  type ProviderTraceStatus,
  type ProviderTraceSummary,
  type ProviderTraceView
} from "./providerTraceApi";
import { formatPortalTimestamp } from "./portalTime";
import { useI18n } from "./i18n";

export function ProviderTraceAccessButton({ onOpen }: { onOpen: () => void }) {
  const { language } = useI18n();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void providerTraceApi
      .access(controller.signal)
      .then(() => setAllowed(true))
      .catch(() => {
        if (!controller.signal.aborted) setAllowed(false);
      });
    return () => controller.abort();
  }, []);

  if (!allowed) return null;
  return (
    <button type="button" className="paper-button" onClick={onOpen}>
      {language === "zh-CN" ? "Provider Trace" : "Provider traces"}
    </button>
  );
}

function categoryLabel(category: ProviderTraceCategory, zh: boolean): string {
  if (category === "tool_calling") return "Tool Calling";
  if (category === "character_turn") return zh ? "角色回合" : "Character Turn";
  if (category === "media_attention") return zh ? "媒体注意力" : "Media Attention";
  if (category === "media_understanding") {
    return zh ? "媒体理解" : "Media Understanding";
  }
  return zh ? "模型调用" : "Model Call";
}

function mediaValue(input: Record<string, unknown>, key: string): string {
  const value = input[key];
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function mediaListLabel(trace: ProviderTraceSummary, zh: boolean): string | null {
  if (trace.category !== "media_understanding") return null;
  const kind = mediaValue(trace.media_input, "media_type");
  const filename = mediaValue(trace.media_input, "filename");
  const host = mediaValue(trace.media_input, "source_host");
  const kindLabel =
    kind === "image"
      ? zh ? "图片" : "Image"
      : kind === "video"
        ? zh ? "视频" : "Video"
        : kind;
  return [kindLabel, filename !== "—" ? filename : null, host !== "—" ? host : null]
    .filter(Boolean)
    .join(" · ");
}

function attentionStanceLabel(value: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    neutral: ["中性", "Neutral"],
    truthful: ["诚实", "Truthful"],
    bluff: ["虚张声势 / 装懂", "Bluff"],
    lie: ["有意撒谎", "Lie"],
    tease: ["逗弄 / 玩笑误导", "Tease"],
    evasive: ["回避", "Evasive"],
    guess: ["猜测", "Guess"],
    uncertain: ["不确定", "Uncertain"]
  };
  const label = labels[value];
  return label ? label[zh ? 0 : 1] : value || "—";
}

function attentionListLabel(trace: ProviderTraceSummary, zh: boolean): string | null {
  if (trace.category !== "media_attention") return null;
  const action = mediaValue(trace.media_attention, "action");
  const stance = mediaValue(trace.media_attention, "response_stance");
  const parts = [
    action !== "—" ? action : null,
    stance !== "—" ? attentionStanceLabel(stance, zh) : null
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : zh ? "等待结构化结果" : "Awaiting structured result";
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
  const [traces, setTraces] = useState<ProviderTraceSummary[]>([]);
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [status, setStatus] = useState<ProviderTraceStatus | "all">("all");
  const [category, setCategory] = useState<ProviderTraceCategory | "all">("all");
  const [ownerId, setOwnerId] = useState("all");
  const [model, setModel] = useState("");
  const [appliedModel, setAppliedModel] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<ProviderTraceView | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pollCycle, setPollCycle] = useState(0);
  const listRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);

  function accountLabel(value: string): string {
    if (!value) return zh ? "系统 / 未归属" : "System / unscoped";
    const account = accounts.find((item) => item.id === value);
    if (!account) return value.slice(0, 12);
    return account.display_name
      ? `${account.display_name} · ${account.email}`
      : account.email;
  }

  async function load(
    targetCursor: string | null = cursor,
    targetModel = appliedModel,
    background = false
  ) {
    listRequestRef.current?.abort();
    const controller = new AbortController();
    listRequestRef.current = controller;
    if (!background) setLoading(true);
    try {
      const next = await providerTraceApi.list({
        limit: 50,
        status,
        category,
        ownerId: ownerId === "all" ? undefined : ownerId,
        model: targetModel,
        cursor: targetCursor,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      setTraces(next.items);
      setNextCursor(next.next_cursor);
      setSelectedId((current) =>
        current && next.items.some((item) => item.trace_id === current)
          ? current
          : next.items[0]?.trace_id ?? null
      );
      setError(null);
    } catch (reason) {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (listRequestRef.current === controller) {
        listRequestRef.current = null;
        if (background) {
          setPollCycle((current) => current + 1);
        } else {
          setLoading(false);
        }
      }
    }
  }

  function resetAndLoad(targetModel = appliedModel) {
    setCursor(null);
    setCursorHistory([]);
    setNextCursor(null);
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
    let active = true;
    void api
      .listAdminUsers()
      .then((items) => {
        if (active) setAccounts(items);
      })
      .catch(() => {
        if (active) setAccounts([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    resetAndLoad();
  }, [status, category, ownerId]);

  useEffect(() => {
    const onVisibilityChange = () => {
      setVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      listRequestRef.current?.abort();
      detailRequestRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!autoRefresh || !visible || page !== 1) return;
    const delay = traces.some((item) => item.status === "pending") ? 5000 : 10000;
    const timer = window.setTimeout(
      () => void load(null, appliedModel, true),
      delay
    );
    return () => window.clearTimeout(timer);
  }, [
    autoRefresh,
    visible,
    page,
    status,
    category,
    ownerId,
    appliedModel,
    traces,
    pollCycle
  ]);

  const selectedSummary = useMemo(
    () => traces.find((item) => item.trace_id === selectedId) ?? null,
    [selectedId, traces]
  );

  useEffect(() => {
    detailRequestRef.current?.abort();
    setSelected(null);
    if (!selectedId) {
      setDetailLoading(false);
      return;
    }
    const controller = new AbortController();
    detailRequestRef.current = controller;
    setDetailLoading(true);
    void providerTraceApi
      .detail(selectedId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setSelected(detail);
          setError(null);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      })
      .finally(() => {
        if (detailRequestRef.current === controller) {
          detailRequestRef.current = null;
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedId, selectedSummary?.updated_at]);

  async function clearAll() {
    const selectedOwner = ownerId === "all" ? undefined : ownerId;
    const confirmed = window.confirm(
      selectedOwner
        ? zh
          ? `清除 ${accountLabel(selectedOwner)} 的 Provider Trace？此操作无法撤销。`
          : `Clear Provider Traces for ${accountLabel(selectedOwner)}? This cannot be undone.`
        : zh
          ? "清除全部 Provider Trace？此操作无法撤销。"
          : "Clear every provider trace? This cannot be undone."
    );
    if (!confirmed) return;
    try {
      const result = await providerTraceApi.clear(selectedOwner);
      setMessage(
        zh
          ? `已清除 ${result.deleted_count} 条 Trace。`
          : `Cleared ${result.deleted_count} traces.`
      );
      setTraces([]);
      setSelectedId(null);
      setSelected(null);
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
              ? "Provider Trace 记录实际发出的外部模型请求，包括角色模型、媒体注意力决策、Tool Calling 与 Media Understanding。Media Attention 会结构化显示角色的 watch / skip 与私下声明的社交姿态；它不是系统事后测谎。Runtime Trace 则记录角色实际上有没有获得 MediaContext。Cache hit 不会伪造 Provider Trace，因为那一轮没有再次调用外部模型。API Key 与 Authorization Header 不会被保存。"
              : "Provider Trace records actual outbound model calls, including Character models, Media Attention decisions, Tool Calling, and Media Understanding. Media Attention shows structured watch/skip plus the Character's privately declared social stance; it is not a post-hoc lie detector. Runtime Trace records whether MediaContext was actually obtained. Cache hits do not create fake Provider Traces because no external model was called again. API keys and Authorization headers are never stored."}
          </p>
        </div>
        <div className="provider-trace-header-actions">
          <button type="button" className="paper-button" onClick={() => void load(cursor)}>
            {loading ? (zh ? "读取中…" : "Loading…") : zh ? "刷新" : "Refresh"}
          </button>
          <button type="button" className="paper-button danger-text" onClick={() => void clearAll()}>
            {ownerId === "all"
              ? zh ? "清除全部" : "Clear all"
              : zh ? "清除此账户" : "Clear account"}
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
          {zh ? "账户" : "Account"}
          <select value={ownerId} onChange={(event) => setOwnerId(event.currentTarget.value)}>
            <option value="all">{zh ? "全部账户" : "All accounts"}</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name || account.email}
              </option>
            ))}
          </select>
        </label>
        <label>
          {zh ? "类型" : "Category"}
          <select
            value={category}
            onChange={(event) =>
              setCategory(event.currentTarget.value as ProviderTraceCategory | "all")
            }
          >
            <option value="all">{zh ? "全部类型" : "All categories"}</option>
            <option value="media_attention">{zh ? "媒体注意力" : "Media Attention"}</option>
            <option value="media_understanding">
              {zh ? "媒体理解" : "Media Understanding"}
            </option>
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
            placeholder="xiaomi/mimo-v2.5"
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
          {zh ? "自适应刷新（5–10 秒）" : "Adaptive refresh (5–10s)"}
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
                  ? "下一次实际模型、媒体注意力、Tool Calling 或 Media Understanding 调用后会出现在这里。"
                  : "The next actual model, Media Attention, Tool Calling, or Media Understanding request will appear here."}
              </p>
            </div>
          ) : (
            <>
              {traces.map((trace) => {
                const mediaLabel = mediaListLabel(trace, zh);
                const attentionLabel = attentionListLabel(trace, zh);
                return (
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
                    {attentionLabel && <small>{attentionLabel}</small>}
                    {mediaLabel && <small>{mediaLabel}</small>}
                    <small>{accountLabel(trace.owner_id)}</small>
                    {trace.tool_names.length > 0 && (
                      <small className="provider-trace-tool-names">
                        {trace.tool_names.join(" · ")}
                      </small>
                    )}
                    <small>{formatPortalTimestamp(trace.created_at, zh)}</small>
                    <small>
                      {trace.latency_ms ?? "—"} ms · {trace.input_tokens ?? "—"} /{" "}
                      {trace.output_tokens ?? "—"} tokens
                    </small>
                    <code>{trace.trace_id.slice(0, 12)}</code>
                  </button>
                );
              })}
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
          {detailLoading && !selected ? (
            <div className="provider-trace-empty">
              <strong>{zh ? "正在读取 Trace 详情…" : "Loading trace detail…"}</strong>
            </div>
          ) : !selected ? (
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
                <div><dt>Account</dt><dd>{accountLabel(selected.owner_id)}</dd></div>
                <div><dt>Category</dt><dd>{categoryLabel(selected.category, zh)}</dd></div>
                <div><dt>Endpoint</dt><dd>{selected.endpoint}</dd></div>
                <div><dt>Trace mode</dt><dd>{selected.trace_mode}</dd></div>
                <div><dt>Status code</dt><dd>{selected.status_code ?? "—"}</dd></div>
                <div><dt>Latency</dt><dd>{selected.latency_ms ?? "—"} ms</dd></div>
                <div><dt>Input tokens</dt><dd>{selected.input_tokens ?? "—"}</dd></div>
                <div><dt>Output tokens</dt><dd>{selected.output_tokens ?? "—"}</dd></div>
                <div><dt>Response model</dt><dd>{selected.response_model || "—"}</dd></div>
                <div><dt>Deployment</dt><dd>{selected.deployment_id || "—"}</dd></div>
                <div><dt>Character</dt><dd>{selected.character_card_id || "—"}</dd></div>
                <div><dt>Created</dt><dd>{formatPortalTimestamp(selected.created_at, zh)}</dd></div>
              </dl>

              {selected.category === "media_attention" && (
                <section className="provider-trace-json-section">
                  <div><h3>{zh ? "角色媒体注意力与社交姿态" : "Character media attention and stance"}</h3></div>
                  <dl className="provider-trace-meta">
                    <div>
                      <dt>{zh ? "是否查看" : "Attention"}</dt>
                      <dd>{mediaValue(selected.media_attention, "action")}</dd>
                    </div>
                    <div>
                      <dt>{zh ? "声明的社交姿态" : "Declared social stance"}</dt>
                      <dd>
                        {attentionStanceLabel(
                          mediaValue(selected.media_attention, "response_stance"),
                          zh
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>{zh ? "查看 / 跳过原因" : "Attention reason"}</dt>
                      <dd>{mediaValue(selected.media_attention, "reason")}</dd>
                    </div>
                    <div>
                      <dt>{zh ? "社交姿态备注" : "Stance note"}</dt>
                      <dd>{mediaValue(selected.media_attention, "stance_reason")}</dd>
                    </div>
                  </dl>
                  <p>
                    {zh
                      ? "这是角色模型在真正下载、字幕提取或 Vision 之前做的私有选择。skip 时后续 Media Understanding 不会运行。bluff / lie / tease 等标签是角色自己声明的社交意图，不是系统事后根据台词做的测谎。要确认角色实际上有没有获得内容感知，请对照 Runtime Trace → Media Epistemic State。"
                      : "This is the Character model's private choice before downloads, transcript extraction, or Vision. A skip prevents Media Understanding from running. Bluff/lie/tease are model-declared social intents, not post-hoc deception labels inferred from dialogue. Check Runtime Trace → Media Epistemic State to confirm whether content perception actually occurred."}
                  </p>
                  {Object.keys(selected.media_attention).length === 0 && (
                    <p>
                      {zh
                        ? "当前 Trace 没有保存结构化决定；这通常表示它来自旧版本、仍在 Pending，或 Provider Trace 处于 metadata-only 模式。"
                        : "No structured decision was persisted for this trace. It may be from an older version, still pending, or recorded in metadata-only trace mode."}
                    </p>
                  )}
                </section>
              )}

              {selected.category === "media_understanding" && (
                <section className="provider-trace-json-section">
                  <div><h3>{zh ? "Media Understanding 输入" : "Media Understanding input"}</h3></div>
                  <dl className="provider-trace-meta">
                    <div><dt>{zh ? "媒体类型" : "Media type"}</dt><dd>{mediaValue(selected.media_input, "media_type")}</dd></div>
                    <div><dt>{zh ? "输入格式" : "Input part"}</dt><dd>{mediaValue(selected.media_input, "input_part_type")}</dd></div>
                    <div><dt>{zh ? "文件名" : "Filename"}</dt><dd>{mediaValue(selected.media_input, "filename")}</dd></div>
                    <div><dt>MIME</dt><dd>{mediaValue(selected.media_input, "mime_type")}</dd></div>
                    <div><dt>{zh ? "大小" : "Size"}</dt><dd>{mediaValue(selected.media_input, "size_bytes")}</dd></div>
                    <div><dt>Source host</dt><dd>{mediaValue(selected.media_input, "source_host")}</dd></div>
                    <div><dt>Media key</dt><dd>{mediaValue(selected.media_input, "media_key")}</dd></div>
                    <div><dt>Source URI</dt><dd>{mediaValue(selected.media_input, "source_uri")}</dd></div>
                  </dl>
                  <p>
                    {zh
                      ? "这里表示 Vision/Video 请求确实发给了外部 Provider。Source URI 已移除 query/fragment；API Key 不会进入 Trace。"
                      : "This confirms that a Vision/Video request was actually sent to the external provider. Source URI query/fragment data is removed, and API keys never enter the trace."}
                  </p>
                </section>
              )}

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
