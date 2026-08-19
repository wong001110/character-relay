import { useEffect, useState } from "react";

import {
  intelligenceProductApi,
  type ServerConversationStructure
} from "./intelligenceProductApi";
import "./conversation-structure.css";

interface Props {
  serverProfileId: string;
  zh: boolean;
}

function stamp(value: string, zh: boolean): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

export function ConversationStructurePanel({ serverProfileId, zh }: Props) {
  const [value, setValue] = useState<ServerConversationStructure | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!serverProfileId) return;
    try {
      setLoading(true);
      setValue(await intelligenceProductApi.conversationStructure(serverProfileId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [serverProfileId]);

  return (
    <section className="deployment-form-wide conversation-structure-sheet">
      <div className="deployment-form-divider conversation-structure-heading">
        <div>
          <strong>{zh ? "Conversation Structure / 对话结构" : "Conversation Structure"}</strong>
          <span>
            {zh
              ? "这是 Server-scoped 的当前对话模型：Burst 只是时间窗口，同一时间可以存在多个 Semantic Thread；旧 current Topic 不再是 routing authority。"
              : "This is the Server-scoped current conversation model: a Burst is only a time window, multiple Semantic Threads may coexist, and legacy current Topic is no longer routing authority."}
          </span>
        </div>
        <button type="button" className="paper-button" disabled={loading} onClick={() => void load()}>
          {zh ? "刷新" : "Refresh"}
        </button>
      </div>
      {error && <small className="deployment-inline-error">{error}</small>}
      {!value ? (
        <small>{zh ? "读取 Server Conversation Structure…" : "Loading Server Conversation Structure…"}</small>
      ) : (
        <div className="conversation-structure-layout">
          <div>
            <span className="tape-label">SEMANTIC THREADS</span>
            <div className="conversation-thread-list">
              {value.threads.map((thread) => (
                <article key={thread.id}>
                  <header>
                    <strong>{thread.label || thread.id}</strong>
                    <span>{thread.status.toUpperCase()}</span>
                  </header>
                  {thread.summary && <p>{thread.summary}</p>}
                  <small>{thread.keywords.slice(0, 8).join(" · ") || "—"}</small>
                  <small>{stamp(thread.last_active_at, zh)}</small>
                </article>
              ))}
              {value.threads.length === 0 && <small>{zh ? "还没有 Semantic Thread。" : "No Semantic Threads yet."}</small>}
            </div>
          </div>
          <div>
            <span className="tape-label">RECENT SEGMENTS</span>
            <div className="conversation-segment-list">
              {value.segments.slice(0, 30).map((segment) => (
                <article key={segment.id}>
                  <header>
                    <strong>{segment.kind}</strong>
                    <span>{segment.thread_action}</span>
                  </header>
                  <p>{segment.summary || (zh ? "Context-only Segment" : "Context-only segment")}</p>
                  <small>
                    {segment.message_ids.length} msg · {segment.source} · confidence {segment.confidence.toFixed(2)}
                  </small>
                  <small>
                    {segment.semantic_thread_id ? `Thread ${segment.semantic_thread_id}` : (zh ? "没有 Thread identity" : "No Thread identity")}
                  </small>
                  <small>
                    {segment.thread_evidence
                      ? (zh ? "会更新 Thread identity" : "Thread identity evidence")
                      : (zh ? "只属于上下文，不更新 identity" : "Context only; does not update identity")}
                  </small>
                </article>
              ))}
              {value.segments.length === 0 && <small>{zh ? "还没有 Segment 记录。" : "No Segment evidence yet."}</small>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
