import { useEffect, useState } from "react";

import {
  loadConversationStructure,
  type ConversationStructureView
} from "./conversationStructureApi";
import "./conversation-structure.css";

interface Props {
  deploymentId: string;
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

export function ConversationStructurePanel({ deploymentId, zh }: Props) {
  const [value, setValue] = useState<ConversationStructureView | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setValue(await loadConversationStructure(deploymentId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [deploymentId]);

  return (
    <section className="deployment-form-wide conversation-structure-sheet">
      <div className="deployment-form-divider conversation-structure-heading">
        <div>
          <strong>{zh ? "Conversation Structure / 对话结构" : "Conversation Structure"}</strong>
          <span>
            {zh
              ? "Burst 只是时间窗口；这里显示同一时间并存的 Semantic Threads，以及每个 Burst 被分成了哪些 Segment。"
              : "A Burst is only a time window. Inspect concurrent Semantic Threads and how each Burst was segmented."}
          </span>
        </div>
        <button type="button" className="paper-button" disabled={loading} onClick={() => void load()}>
          {zh ? "刷新" : "Refresh"}
        </button>
      </div>
      {error && <small className="deployment-inline-error">{error}</small>}
      {!value ? (
        <small>{zh ? "读取 Conversation Structure…" : "Loading conversation structure…"}</small>
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
              {value.segments.slice(0, 20).map((segment) => (
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
                    {segment.thread_evidence
                      ? (zh ? "会更新 Thread identity" : "Thread evidence")
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
