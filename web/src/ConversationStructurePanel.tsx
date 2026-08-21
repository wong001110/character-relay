import { useEffect, useMemo, useState } from "react";

import type { CharacterDeployment } from "./deploymentApi";
import {
  loadConversationStructure,
  type ConversationStructureView
} from "./conversationStructureApi";
import "./conversation-structure.css";

interface Props {
  deployments: CharacterDeployment[];
  zh: boolean;
}

type NotebookTab =
  | "threads"
  | "relations"
  | "episodes"
  | "entities"
  | "beliefs"
  | "social";

function stamp(value: string, zh: boolean): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

function shortRef(value: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function confidence(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "—";
}

export function ConversationStructurePanel({ deployments, zh }: Props) {
  const [deploymentId, setDeploymentId] = useState("");
  const [tab, setTab] = useState<NotebookTab>("threads");
  const [value, setValue] = useState<ConversationStructureView | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (deploymentId && deployments.some((item) => item.id === deploymentId)) return;
    setDeploymentId(deployments[0]?.id ?? "");
  }, [deploymentId, deployments]);

  const deployment = useMemo(
    () => deployments.find((item) => item.id === deploymentId),
    [deploymentId, deployments]
  );

  async function load(targetId = deploymentId) {
    if (!targetId) {
      setValue(null);
      return;
    }
    try {
      setLoading(true);
      setValue(await loadConversationStructure(targetId));
      setError("");
    } catch (reason) {
      setValue(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(deploymentId);
  }, [deploymentId]);

  const tabs: Array<{ key: NotebookTab; en: string; zh: string; count: number }> = [
    {
      key: "threads",
      en: "Threads",
      zh: "对话线",
      count: (value?.threads.length ?? 0) + (value?.segments.length ?? 0)
    },
    { key: "relations", en: "Relations", zh: "关系证据", count: value?.relations.length ?? 0 },
    { key: "episodes", en: "Episodes", zh: "事件记录", count: value?.episodes.length ?? 0 },
    {
      key: "entities",
      en: "Entities",
      zh: "实体 / 缺口",
      count: (value?.entities.length ?? 0) + (value?.knowledge_gaps.length ?? 0)
    },
    { key: "beliefs", en: "Beliefs", zh: "记忆信念", count: value?.beliefs.length ?? 0 },
    {
      key: "social",
      en: "Social",
      zh: "社交证据",
      count: (value?.social_events.length ?? 0) + (value?.impressions.length ?? 0)
    }
  ];

  return (
    <section className="deployment-form-wide conversation-structure-sheet">
      <div className="deployment-form-divider conversation-structure-heading">
        <div>
          <span className="tape-label">CONVERSATION AUTHORITY V3</span>
          <strong>{zh ? "Conversation Structure / 对话结构" : "Conversation Structure"}</strong>
          <span>
            {zh
              ? "以 Thread、可逆 Membership 与证据关系解释群聊。Burst 只是时间批次；不再存在 Topic routing authority。"
              : "Group chat is interpreted through Threads, reversible Memberships, and evidence relations. Bursts are only temporal batches; Topic routing authority is gone."}
          </span>
        </div>
        <div className="conversation-structure-controls">
          <label>
            <span>{zh ? "角色" : "Character"}</span>
            <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
              {deployments.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.character_display_name || item.character_card_id}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="paper-button"
            disabled={loading || !deploymentId}
            onClick={() => void load()}
          >
            {zh ? "刷新" : "Refresh"}
          </button>
        </div>
      </div>

      {deployment && (
        <div className="conversation-structure-context-note sticky-note">
          <strong>{deployment.character_display_name || deployment.character_card_id}</strong>
          <span>
            {zh
              ? "这里显示这个角色在当前 Server 可使用的 Conversation / Knowledge / Social 解释证据。"
              : "This notebook shows Conversation, Knowledge, and Social interpretation evidence available to this Character in the current Server."}
          </span>
        </div>
      )}

      {error && <small className="deployment-inline-error">{error}</small>}
      {deployments.length === 0 && (
        <small>{zh ? "这个 Server 还没有角色 Deployment。" : "No Character deployments on this Server yet."}</small>
      )}

      {value && (
        <>
          <nav className="conversation-index-tabs" aria-label={zh ? "对话结构索引" : "Conversation structure index"}>
            {tabs.map((item) => (
              <button
                type="button"
                key={item.key}
                className={tab === item.key ? "is-active" : ""}
                onClick={() => setTab(item.key)}
              >
                <span>{zh ? item.zh : item.en}</span>
                <small>{item.count}</small>
              </button>
            ))}
          </nav>

          {tab === "threads" && (
            <div className="conversation-structure-layout">
              <div>
                <span className="tape-label">ACTIVE / RECENT THREADS</span>
                <div className="conversation-thread-list">
                  {value.threads.map((thread) => (
                    <article key={thread.id}>
                      <header>
                        <strong>{thread.canonical_label || shortRef(thread.id)}</strong>
                        <span>{thread.status.toUpperCase()}</span>
                      </header>
                      <p className="conversation-anchor-summary">
                        <b>{zh ? "Anchor" : "Anchor"}:</b> {thread.anchor_summary || "—"}
                      </p>
                      <p>
                        <b>{zh ? "Working" : "Working"}:</b> {thread.working_summary || "—"}
                      </p>
                      <small>
                        {thread.participant_ids.length} participants · {thread.active_entity_ids.length} entities · {stamp(thread.last_active_at, zh)}
                      </small>
                      <small>Thread {shortRef(thread.id)}</small>
                    </article>
                  ))}
                  {value.threads.length === 0 && (
                    <small>{zh ? "还没有 Conversation Thread。" : "No Conversation Threads yet."}</small>
                  )}
                </div>
              </div>

              <div>
                <span className="tape-label">SEGMENTS + MEMBERSHIPS</span>
                <div className="conversation-segment-list">
                  {value.segments.slice(0, 50).map((segment) => (
                    <article key={segment.id}>
                      <header>
                        <strong>{segment.kind}</strong>
                        <span>{segment.membership_relation}</span>
                      </header>
                      <p>{segment.summary || (zh ? "只有上下文，没有摘要" : "Context-only segment")}</p>
                      <small>
                        {segment.message_ids.length} msg · {segment.source} · segment {confidence(segment.confidence)}
                      </small>
                      <small>
                        {segment.thread_id
                          ? `Thread ${shortRef(segment.thread_id)} · membership ${confidence(segment.membership_confidence)}`
                          : (zh ? "Membership unresolved" : "Membership unresolved")}
                      </small>
                    </article>
                  ))}
                  {value.segments.length === 0 && (
                    <small>{zh ? "还没有 Segment。" : "No Segments yet."}</small>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === "relations" && (
            <div className="conversation-evidence-grid">
              {value.relations.map((relation) => (
                <article key={relation.id} className="conversation-evidence-card">
                  <header>
                    <strong>{relation.relation_type}</strong>
                    <span>{relation.status}</span>
                  </header>
                  <p>
                    {shortRef(relation.source_message_id)} → {relation.target_ref_type}:{" "}
                    {shortRef(relation.target_ref)}
                  </p>
                  <small>
                    {relation.relation_class} · {relation.source} · confidence {confidence(relation.confidence)}
                  </small>
                  <small>{relation.evidence_refs.length} evidence refs · {stamp(relation.created_at, zh)}</small>
                  {relation.supersedes_relation_id && (
                    <small>{zh ? "取代" : "Supersedes"} {shortRef(relation.supersedes_relation_id)}</small>
                  )}
                </article>
              ))}
              {value.relations.length === 0 && (
                <small>{zh ? "还没有 Message Relation。" : "No Message Relations yet."}</small>
              )}
            </div>
          )}

          {tab === "episodes" && (
            <div className="conversation-evidence-grid">
              {value.episodes.map((episode) => (
                <article key={episode.id} className="conversation-evidence-card">
                  <header>
                    <strong>{episode.summary || shortRef(episode.id)}</strong>
                    <span>{episode.status}</span>
                  </header>
                  <p>{episode.key_events.slice(0, 4).join(" · ") || "—"}</p>
                  <small>
                    Thread {shortRef(episode.conversation_thread_id)} · {episode.segment_ids.length} segments · {episode.source_message_ids.length} messages
                  </small>
                  <small>
                    {episode.checkpoint_reason || "checkpoint"} · {stamp(episode.ended_at, zh)}
                  </small>
                </article>
              ))}
              {value.episodes.length === 0 && (
                <small>{zh ? "还没有 Episode。" : "No Episodes yet."}</small>
              )}
            </div>
          )}

          {tab === "entities" && (
            <div className="conversation-structure-layout">
              <div>
                <span className="tape-label">ENTITY GROUNDING</span>
                <div className="conversation-evidence-grid">
                  {value.entities.map((entity) => (
                    <article key={entity.id} className="conversation-evidence-card">
                      <header>
                        <strong>{entity.canonical_name || shortRef(entity.id)}</strong>
                        <span>{entity.status}</span>
                      </header>
                      <p>{entity.entity_type}</p>
                      <small>{entity.aliases.join(" · ") || (zh ? "没有 alias" : "No aliases")}</small>
                      <small>{entity.source_refs.length} source refs · Entity {shortRef(entity.id)}</small>
                      {entity.merged_into_entity_id && (
                        <small>{zh ? "已合并到" : "Merged into"} {shortRef(entity.merged_into_entity_id)}</small>
                      )}
                    </article>
                  ))}
                </div>
              </div>
              <div>
                <span className="tape-label">KNOWLEDGE GAPS</span>
                <div className="conversation-evidence-grid">
                  {value.knowledge_gaps.map((gap) => (
                    <article key={gap.id} className="conversation-evidence-card knowledge-gap-card">
                      <header>
                        <strong>{zh ? "未知资料" : "Knowledge gap"}</strong>
                        <span>{gap.resolution_state}</span>
                      </header>
                      <p>{gap.missing_fields.join(" · ") || "—"}</p>
                      <small>
                        Entity {shortRef(gap.entity_id)} · importance {confidence(gap.importance)}
                      </small>
                      <small>
                        {gap.discovery_requested
                          ? (zh ? "已交给现有 Discovery 查找" : "Existing Discovery requested")
                          : (zh ? "暂不需要 Discovery" : "Discovery not required yet")}
                      </small>
                    </article>
                  ))}
                  {value.knowledge_gaps.length === 0 && (
                    <small>{zh ? "目前没有 unresolved Knowledge Gap。" : "No unresolved Knowledge Gaps."}</small>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === "beliefs" && (
            <div className="conversation-evidence-grid">
              {value.beliefs.map((belief) => (
                <article key={belief.id} className="conversation-evidence-card belief-card">
                  <header>
                    <strong>{belief.predicate}</strong>
                    <span>{belief.status}</span>
                  </header>
                  <p>
                    {belief.subject_ref || shortRef(belief.subject_entity_id)} → {belief.value_text}
                  </p>
                  <small>
                    {belief.authority_class} · authority {confidence(belief.authority_score)} · confidence {confidence(belief.confidence)}
                  </small>
                  <small>
                    {belief.authored ? (zh ? "Canonical / authored" : "Canonical / authored") : (zh ? "Learned claim" : "Learned claim")} · {belief.evidence_refs.length} evidence · {belief.dependency_edge_ids.length} dependencies
                  </small>
                  {belief.supersedes_belief_id && (
                    <small>{zh ? "取代 Belief" : "Supersedes Belief"} {shortRef(belief.supersedes_belief_id)}</small>
                  )}
                  <small>{stamp(belief.updated_at, zh)}</small>
                </article>
              ))}
              {value.beliefs.length === 0 && (
                <small>{zh ? "还没有 Belief v3 记录。" : "No Belief v3 records yet."}</small>
              )}
            </div>
          )}

          {tab === "social" && (
            <div className="conversation-structure-layout">
              <div>
                <span className="tape-label">SOCIAL EVENTS</span>
                <div className="conversation-evidence-grid">
                  {value.social_events.map((event) => (
                    <article key={event.id} className="conversation-evidence-card">
                      <header>
                        <strong>{event.event_type}</strong>
                        <span>{event.status}</span>
                      </header>
                      <p>{event.target_type}:{event.target_key}</p>
                      <small>{event.reason || "—"}</small>
                      <small>
                        confidence {confidence(event.confidence)} · segment {shortRef(event.source_segment_id)} · episode {shortRef(event.source_episode_id)}
                      </small>
                    </article>
                  ))}
                </div>
              </div>
              <div>
                <span className="tape-label">REVISABLE IMPRESSIONS</span>
                <div className="conversation-evidence-grid">
                  {value.impressions.map((impression) => (
                    <article key={impression.id} className="conversation-evidence-card impression-card">
                      <header>
                        <strong>{impression.target_type}:{impression.target_key}</strong>
                        <span>{impression.status}</span>
                      </header>
                      <p>{impression.summary}</p>
                      <small>{impression.observations.slice(0, 4).join(" · ") || "—"}</small>
                      <small>
                        confidence {confidence(impression.confidence)} · {impression.evidence_refs.length} evidence refs
                      </small>
                      {impression.supersedes_impression_id && (
                        <small>{zh ? "取代 Impression" : "Supersedes Impression"} {shortRef(impression.supersedes_impression_id)}</small>
                      )}
                    </article>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
