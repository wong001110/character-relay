import { useEffect, useState } from "react";

import {
  intelligenceProductApi,
  type ServerParticipationIntelligence
} from "./intelligenceProductApi";

interface Props {
  serverProfileId: string;
  zh: boolean;
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

export function ParticipationIntelligencePanel({ serverProfileId, zh }: Props) {
  const [data, setData] = useState<ServerParticipationIntelligence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    if (!serverProfileId) return;
    try {
      setLoading(true);
      setError("");
      setData(await intelligenceProductApi.participation(serverProfileId));
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
    <section className="paper-sheet participation-vnext-panel">
      <header className="intelligence-product-heading">
        <div>
          <span className="tape-label">PARTICIPATION / REPLY PLANNER</span>
          <h2>{zh ? "角色为什么在这个 Burst 里说话" : "Why a Character spoke in this Burst"}</h2>
          <p>
            {zh
              ? "当前 Smart Participation 使用 Burst → Segments → Semantic Threads → per-Character Segment Reply Planner。旧的 Topics / Keywords / Group Role Profile 不再作为 Portal 的主要配置模型。"
              : "Current Smart Participation uses Burst → Segments → Semantic Threads → a per-Character Segment Reply Planner. Legacy Topics / Keywords / Group Role profiles are no longer the primary Portal model."}
          </p>
        </div>
        <button type="button" className="paper-button" disabled={loading} onClick={() => void load()}>
          {zh ? "刷新" : "Refresh"}
        </button>
      </header>

      {error && <small className="deployment-inline-error">{error}</small>}
      {!data ? (
        <p>{loading ? (zh ? "读取 Participation Intelligence…" : "Loading Participation Intelligence…") : "—"}</p>
      ) : (
        <>
          <div className="participation-vnext-summary">
            <article><span>{zh ? "Resolver" : "Resolver"}</span><strong>{data.resolver_version}</strong></article>
            <article><span>{zh ? "Planner" : "Planner"}</span><strong>{data.planner_model}</strong></article>
            <article><span>{zh ? "最近 Reply Target" : "Recent reply targets"}</span><strong>{data.recent_reply_decisions.length}</strong></article>
          </div>

          <section className="participation-vnext-section">
            <div className="intelligence-section-title">
              <span className="tape-label">DEPLOYMENTS</span>
              <strong>{zh ? "参与模式与最近 admission" : "Participation mode & latest admission"}</strong>
            </div>
            <div className="participation-deployment-grid">
              {data.deployments.map((item) => (
                <article key={item.deployment_id}>
                  <header><strong>{item.character_display_name}</strong><span>{item.status.toUpperCase()}</span></header>
                  <p>{item.participation_mode.replaceAll("_", " ")}</p>
                  <small>{zh ? "最近获准参与：" : "Last admitted: "}{stamp(item.last_admitted_at, zh)}</small>
                  {(item.last_channel_id || item.last_thread_id) && <small>#{item.last_channel_id}{item.last_thread_id ? ` / ${item.last_thread_id}` : ""}</small>}
                </article>
              ))}
            </div>
          </section>

          <section className="participation-vnext-section">
            <div className="intelligence-section-title">
              <span className="tape-label">RECENT SEGMENT TARGETS</span>
              <strong>{zh ? "Reply Planner 已持久化的选择" : "Persisted Reply Planner selections"}</strong>
            </div>
            {data.recent_reply_decisions.length === 0 ? (
              <div className="intelligence-empty-note">
                <strong>{zh ? "还没有 vNext Reply Target 记录" : "No vNext Reply Target evidence yet"}</strong>
                <p>{zh ? "新的 Smart Participation turn 通过 Segment Reply Planner 后会写入这里；旧历史不会伪造补齐。" : "New Smart Participation turns are recorded here after Segment Reply Planner selection. Historical turns are not backfilled with invented evidence."}</p>
              </div>
            ) : (
              <div className="reply-decision-list">
                {data.recent_reply_decisions.map((item, index) => (
                  <article key={`${item.source_message_id}:${item.deployment_id}:${index}`}>
                    <header>
                      <div><strong>{item.character_display_name}</strong><span>{item.authoritative ? "AUTHORITATIVE" : item.plan_kind.toUpperCase()}</span></div>
                      <small>{stamp(item.created_at, zh)}</small>
                    </header>
                    <div className="reply-decision-route">
                      <span>Burst <b>{item.burst_id || "—"}</b></span>
                      <span>Segment <b>{item.segment_id}</b></span>
                      <span>Thread <b>{item.semantic_thread_id || "context-only"}</b></span>
                    </div>
                    <p>{item.reason.replaceAll("_", " ")}</p>
                    {item.guidance && <blockquote>{item.guidance}</blockquote>}
                    <small>score {item.score.toFixed(3)} · #{item.channel_id}{item.thread_id ? ` / ${item.thread_id}` : ""}</small>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="participation-vnext-section">
            <div className="intelligence-section-title">
              <span className="tape-label">DURABLE ADMISSION WINDOWS</span>
              <strong>{zh ? "Server 级 cooldown / rate evidence" : "Server cooldown / rate evidence"}</strong>
            </div>
            <div className="participation-scope-list">
              {data.scopes.slice(0, 12).map((item, index) => (
                <div key={`${item.channel_id}:${item.thread_id}:${index}`}>
                  <strong>#{item.channel_id}{item.thread_id ? ` / ${item.thread_id}` : ""}</strong>
                  <span>{zh ? "窗口次数" : "window count"} {item.window_count}</span>
                  <small>{stamp(item.last_admitted_at, zh)}</small>
                </div>
              ))}
              {data.scopes.length === 0 && <small>{zh ? "暂无 durable admission evidence。" : "No durable admission evidence yet."}</small>}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
