import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { TopicNote } from "./components/shared";
import {
  EmptyState,
  InspectorSection,
  Select,
  Spinner,
  StickyLabel,
  StickyNote,
  Toast
} from "./components/ui";
import {
  conversationIntelligenceApi,
  type CharacterIntelligenceSnapshot,
  type LearnedStateInspection,
  type TopicTimelineSnapshot
} from "./conversationIntelligenceApi";
import type { DiscordServerCatalog, DiscordServerProfile } from "./deploymentApi";

interface Props {
  cards: CharacterCard[];
  profile: DiscordServerProfile;
  catalog?: DiscordServerCatalog;
  zh: boolean;
}

const stateOrder = [
  "interest",
  "expertise",
  "stance",
  "relationship",
  "conversation_ownership",
  "salience",
  "participation_fatigue"
];

function stateLabel(value: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    interest: ["Interest", "兴趣"],
    expertise: ["Expertise", "专长"],
    stance: ["Stance", "立场"],
    relationship: ["Relationship", "关系"],
    conversation_ownership: ["Conversation ownership", "话题参与所有权"],
    salience: ["Salience", "当前显著性"],
    participation_fatigue: ["Participation fatigue", "参与疲劳"]
  };
  const item = labels[value];
  return item ? (zh ? item[1] : item[0]) : value.replaceAll("_", " ");
}

function formatSeconds(value: number, zh: boolean): string {
  if (value < 3600) return `${Math.round(value / 60)} ${zh ? "分钟" : "min"}`;
  if (value < 86400) return `${Math.round(value / 3600)} ${zh ? "小时" : "hr"}`;
  return `${Math.round(value / 86400)} ${zh ? "天" : "days"}`;
}

function formatValue(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
}

function meterPosition(value: number): number {
  return Math.max(0, Math.min(100, (value + 1) * 50));
}

function stateSort(left: LearnedStateInspection, right: LearnedStateInspection): number {
  const leftIndex = stateOrder.indexOf(left.state_type);
  const rightIndex = stateOrder.indexOf(right.state_type);
  if (leftIndex !== rightIndex) return (leftIndex < 0 ? 999 : leftIndex) - (rightIndex < 0 ? 999 : rightIndex);
  return Math.abs(right.current_value) - Math.abs(left.current_value);
}

export function ConversationIntelligenceInspector({ cards, profile, catalog, zh }: Props) {
  const [characterId, setCharacterId] = useState(cards[0]?.id ?? "");
  const [channelId, setChannelId] = useState(catalog?.channels[0]?.id ?? "");
  const [character, setCharacter] = useState<CharacterIntelligenceSnapshot | null>(null);
  const [topics, setTopics] = useState<TopicTimelineSnapshot | null>(null);
  const [characterError, setCharacterError] = useState("");
  const [topicError, setTopicError] = useState("");
  const [loadingCharacter, setLoadingCharacter] = useState(false);
  const [loadingTopics, setLoadingTopics] = useState(false);

  const selectedCard = cards.find((item) => item.id === characterId) ?? null;
  const channels = useMemo(
    () => (catalog?.channels ?? []).filter(
      (item) =>
        !profile.excluded_channel_ids.includes(item.id)
        && (!item.category_id || !profile.excluded_category_ids.includes(item.category_id))
    ),
    [catalog, profile.excluded_category_ids, profile.excluded_channel_ids]
  );

  useEffect(() => {
    if (!cards.some((item) => item.id === characterId)) setCharacterId(cards[0]?.id ?? "");
  }, [cards, characterId]);

  useEffect(() => {
    if (!channels.some((item) => item.id === channelId)) setChannelId(channels[0]?.id ?? "");
  }, [channelId, channels]);

  useEffect(() => {
    if (!characterId) { setCharacter(null); return; }
    let active = true;
    setLoadingCharacter(true);
    setCharacterError("");
    void conversationIntelligenceApi.character(characterId)
      .then((value) => { if (active) setCharacter(value); })
      .catch((reason: unknown) => { if (active) setCharacterError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (active) setLoadingCharacter(false); });
    return () => { active = false; };
  }, [characterId]);

  useEffect(() => {
    if (!channelId) { setTopics(null); return; }
    let active = true;
    setLoadingTopics(true);
    setTopicError("");
    void conversationIntelligenceApi.topics({ connectionId: profile.connection_id, guildId: profile.guild_id, channelId })
      .then((value) => { if (active) setTopics(value); })
      .catch((reason: unknown) => { if (active) setTopicError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (active) setLoadingTopics(false); });
    return () => { active = false; };
  }, [channelId, profile.connection_id, profile.guild_id]);

  const learnedItems = [...(character?.items ?? [])].sort(stateSort);
  const currentTopic = topics?.items.find((item) => item.id === topics.current_topic_id) ?? null;

  return (
    <section className="conversation-intelligence-inspector conversation-intelligence-v3">
      <header className="conversation-intelligence-head paper-sheet">
        <div>
          <StickyLabel variant="link">CONVERSATION INTELLIGENCE</StickyLabel>
          <h2>{zh ? "角色状态与 Topic 研究页" : "Character State & Topic Research Page"}</h2>
          <p>{zh ? "Character Card 是核心真相；这里展示从真实会话证据推导、并随时间衰减的状态。" : "Character Card remains authoritative; this page shows derived state that evolves with evidence and temporal decay."}</p>
        </div>
      </header>

      <div className="conversation-intelligence-grid">
        <InspectorSection
          className="intelligence-character-panel"
          eyebrow={zh ? "角色 / AUTHORITATIVE + DERIVED" : "Character / authoritative + derived"}
          title={selectedCard?.display_name ?? (zh ? "选择角色" : "Choose character")}
          actions={<Select value={characterId} onChange={(event) => setCharacterId(event.currentTarget.value)}>{cards.map((card) => <option key={card.id} value={card.id}>{card.display_name}</option>)}</Select>}
        >
          {selectedCard && (
            <StickyNote className="intelligence-authority-note" variant="character">
              <StickyLabel variant="neutral">CHARACTER CARD / AUTHORITATIVE</StickyLabel>
              <p>{selectedCard.persona_summary}</p>
              <div className="intelligence-chip-row">{[...selectedCard.traits, ...selectedCard.tags].slice(0, 10).map((item) => <StickyLabel variant="neutral" key={item}>{item}</StickyLabel>)}</div>
            </StickyNote>
          )}

          <div className="intelligence-section-title">
            <div><strong>{zh ? "Learned State / derived" : "Learned State / derived"}</strong><small>{zh ? "Current value 已包含时间衰减" : "Current value includes temporal decay"}</small></div>
            {loadingCharacter && <Spinner size="sm" label={zh ? "读取角色状态" : "Loading character state"} />}
          </div>

          {characterError && <Toast tone="danger" title={zh ? "无法读取 Learned State" : "Learned State unavailable"}>{characterError}</Toast>}
          {!loadingCharacter && !characterError && learnedItems.length === 0 && <EmptyState title={zh ? "还没有 Learned State evidence" : "No Learned State evidence yet"} description={zh ? "当角色在真实会话里累积证据后，状态会出现在这里。" : "Derived state appears here after the character accumulates evidence in real conversations."} />}

          <div className="learned-state-list">
            {learnedItems.map((item) => (
              <details className="learned-state-card" key={item.id}>
                <summary>
                  <div><span>{stateLabel(item.state_type, zh)}</span><strong>{item.subject_label || item.subject_key}</strong></div>
                  <div className="learned-state-value"><strong>{formatValue(item.current_value)}</strong><small>{zh ? "当前" : "current"}</small></div>
                </summary>
                <div className="learned-state-meter" aria-label="Learned state value"><span className="learned-state-zero" /><i style={{ left: `${meterPosition(item.current_value)}%` }} /></div>
                <div className="learned-state-metrics">
                  <div><span>Stored</span><strong>{formatValue(item.stored_value)}</strong></div>
                  <div><span>Current</span><strong>{formatValue(item.current_value)}</strong></div>
                  <div><span>Confidence</span><strong>{item.current_confidence.toFixed(3)}</strong></div>
                  <div><span>Half-life</span><strong>{formatSeconds(item.half_life_seconds, zh)}</strong></div>
                  <div><span>Evidence</span><strong>+{item.positive_evidence_count} / -{item.negative_evidence_count}</strong></div>
                  <div><span>Contradictions</span><strong>{item.contradiction_count}</strong></div>
                </div>
                <p className="learned-state-last-evidence">{zh ? "最后 evidence" : "Last evidence"}: {new Date(item.last_evidence_at).toLocaleString()}</p>
                <div className="learned-state-provenance">
                  <strong>{zh ? "最近变化证据" : "Recent evidence"}</strong>
                  {item.provenance.length === 0 ? <p>{zh ? "没有可显示的 provenance。" : "No provenance is available."}</p> : item.provenance.slice().reverse().map((evidence, index) => (
                    <article key={`${item.id}-${evidence.recorded_at ?? index}`}>
                      <div><strong>{evidence.reason_code || evidence.source_type || "evidence"}</strong><span className={evidence.delta >= 0 ? "is-positive" : "is-negative"}>{formatValue(evidence.delta)} × {evidence.confidence.toFixed(2)}</span></div>
                      <small>{evidence.recorded_at ? new Date(evidence.recorded_at).toLocaleString() : "—"}{evidence.contradiction ? ` · ${zh ? "矛盾证据" : "contradiction"}` : ""}</small>
                      {(evidence.source_burst_id || evidence.source_message_id) && <code>{evidence.source_burst_id || evidence.source_message_id}</code>}
                    </article>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </InspectorSection>

        <InspectorSection
          className="intelligence-topic-panel"
          eyebrow={zh ? "Conversation Scope / TOPIC" : "Conversation scope / topic"}
          title={profile.guild_name || profile.name}
          actions={<Select value={channelId} onChange={(event) => setChannelId(event.currentTarget.value)}>{channels.map((channel) => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}</Select>}
        >
          {topicError && <Toast tone="danger" title={zh ? "无法读取 Topic" : "Topic data unavailable"}>{topicError}</Toast>}
          {loadingTopics && <div className="intelligence-loading"><Spinner label={zh ? "读取 Topic" : "Loading topics"} /></div>}
          {!loadingTopics && !channelId && <EmptyState title={zh ? "没有可观察 Channel" : "No observable channels"} />}

          {currentTopic ? (
            <TopicNote
              className="current-topic-card-v3"
              topic={currentTopic.topic_label || (zh ? "未命名 Topic" : "Untitled topic")}
              participants={`${currentTopic.message_count} ${zh ? "条消息" : "messages"} · capsule v${currentTopic.capsule_version}`}
              status={currentTopic.status}
            >
              <p>{currentTopic.summary || (zh ? "暂无 summary。" : "No summary yet.")}</p>
            </TopicNote>
          ) : !loadingTopics && channelId ? (
            <EmptyState title={zh ? "当前没有 active Topic" : "No active topic"} description={zh ? "新会话证据出现后，Current Topic 会以便签形式附在这里。" : "The Current Topic note appears here when new conversation evidence creates one."} />
          ) : null}

          {currentTopic && (
            <div className="topic-meta-grid">
              <div><span>{zh ? "开始" : "Started"}</span><strong>{new Date(currentTopic.started_at).toLocaleString()}</strong></div>
              <div><span>{zh ? "最近活动" : "Last active"}</span><strong>{new Date(currentTopic.last_active_at).toLocaleString()}</strong></div>
              <div><span>{zh ? "关键词" : "Keywords"}</span><strong>{currentTopic.keywords.join(" · ") || "—"}</strong></div>
              <div><span>{zh ? "Open loops" : "Open loops"}</span><strong>{currentTopic.open_loops.length}</strong></div>
            </div>
          )}

          <div className="topic-timeline">
            <div className="intelligence-section-title"><div><strong>{zh ? "Topic Timeline" : "Topic timeline"}</strong><small>{zh ? "最近 20 个 Topic capsule" : "Most recent 20 topic capsules"}</small></div></div>
            {(topics?.items ?? []).map((topic) => (
              <article className={`topic-timeline-item is-${topic.status}`} key={topic.id}>
                <span className="topic-timeline-dot" />
                <div><div className="topic-timeline-heading"><strong>{topic.topic_label || (zh ? "未命名 Topic" : "Untitled topic")}</strong><StickyLabel variant={topic.status === "active" ? "success" : "neutral"}>{topic.status}</StickyLabel></div><p>{topic.summary}</p><small>{new Date(topic.last_active_at).toLocaleString()} · {topic.message_count} {zh ? "条消息" : "messages"} · v{topic.capsule_version}</small></div>
              </article>
            ))}
            {!loadingTopics && topics?.items.length === 0 && <EmptyState title={zh ? "这个 Channel 还没有 Topic history" : "No topic history for this channel"} />}
          </div>
        </InspectorSection>
      </div>
    </section>
  );
}