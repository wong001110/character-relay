import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { TopicNote } from "./components/shared";
import {
  Button,
  EmptyState,
  InspectorSection,
  PageFlag,
  PageFlagGroup,
  PaperCard,
  Select,
  Spinner,
  StickyLabel,
  StickyNote,
  Textarea,
  Toast
} from "./components/ui";
import {
  conversationIntelligenceApi,
  type CharacterIntelligenceSnapshot,
  type CharacterMemorySnapshot,
  type CharacterMindHistory,
  type CoreMemorySnapshot,
  type CurrentInterestSnapshot,
  type DerivedResetResult,
  type LearnedStateInspection,
  type SocialEgoGraph,
  type TopicDecisionTimeline,
  type TopicOverview,
  type TopicTimelineSnapshot
} from "./conversationIntelligenceApi";
import type { DiscordServerCatalog, DiscordServerProfile } from "./deploymentApi";
import "./conversation-intelligence-control-plane.css";

interface Props {
  cards: CharacterCard[];
  profile: DiscordServerProfile;
  catalog?: DiscordServerCatalog;
  zh: boolean;
}

type IntelligenceTab = "overview" | "topics" | "memories" | "mind" | "social" | "hygiene";
type SocialIdentityNeighbor = SocialEgoGraph["items"][number] & {
  avatar_url?: string;
  discord_user_id?: string;
  is_bot?: boolean;
};
type SocialIdentityGraph = Omit<SocialEgoGraph, "items"> & {
  character_avatar_url?: string;
  items: SocialIdentityNeighbor[];
};

const tabTones = ["lavender", "blue", "yellow", "mint", "rose", "peach"] as const;
const nowStateTypes = new Set(["salience", "conversation_ownership", "participation_fatigue"]);
const developingStateTypes = new Set(["interest", "expertise", "stance"]);

function stateLabel(value: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    interest: ["Interest", "兴趣"],
    expertise: ["Expertise", "专长"],
    stance: ["Stance", "立场"],
    relationship: ["Relationship", "关系"],
    conversation_ownership: ["Conversation ownership", "话题参与倾向"],
    salience: ["Salience", "当前显著性"],
    participation_fatigue: ["Participation fatigue", "参与疲劳"]
  };
  const item = labels[value];
  return item ? (zh ? item[1] : item[0]) : value.replaceAll("_", " ");
}

function formatValue(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
}

function formatAge(seconds: number, zh: boolean): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}${zh ? " 分钟" : "m"}`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}${zh ? " 小时" : "h"}`;
  return `${Math.round(seconds / 86400)}${zh ? " 天" : "d"}`;
}

function percent(value: number): number {
  return Math.max(0, Math.min(100, Math.abs(value) * 100));
}

function trendGlyph(value: string): string {
  if (value === "rising") return "↗";
  if (value === "falling") return "↘";
  return "→";
}

function StateCard({ item, zh }: { item: LearnedStateInspection; zh: boolean }) {
  return (
    <PaperCard className="ci-state-card">
      <div className="ci-state-card__head">
        <div><small>{stateLabel(item.state_type, zh)}</small><strong>{item.subject_label || item.subject_key}</strong></div>
        <strong>{formatValue(item.current_value)}</strong>
      </div>
      <div className="ci-strength-track"><i style={{ width: `${percent(item.current_value)}%` }} /></div>
      <div className="ci-state-meta">
        <span>confidence {item.current_confidence.toFixed(2)}</span>
        <span>{item.evidence_count} evidence</span>
        <span>half-life {formatAge(item.half_life_seconds, zh)}</span>
      </div>
      {item.provenance[0] && <small>{item.provenance[item.provenance.length - 1]?.reason_code || item.provenance[item.provenance.length - 1]?.source_type}</small>}
    </PaperCard>
  );
}

function SocialGraphCanvas({ graph }: { graph: SocialEgoGraph }) {
  const identityGraph = graph as SocialIdentityGraph;
  const nodes = identityGraph.items.slice(0, 8);
  const centerX = 180;
  const centerY = 142;
  const radius = 104;
  const positions = nodes.map((item, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(1, nodes.length);
    return { item, index, x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius };
  });
  return (
    <svg className="ci-social-svg" viewBox="0 0 360 320" role="img" aria-label="Character social ego graph">
      <defs>
        <clipPath id="ci-social-center-avatar"><circle cx={centerX} cy={centerY} r="37" /></clipPath>
        {positions.map(({ item, index, x, y }) => (
          <clipPath key={`clip-${item.subject_key}`} id={`ci-social-avatar-${index}`}>
            <circle cx={x} cy={y} r={21 + Math.abs(item.value) * 7} />
          </clipPath>
        ))}
      </defs>
      {positions.map(({ item, x, y }) => (
        <line
          key={`edge-${item.subject_key}`}
          x1={centerX}
          y1={centerY}
          x2={x}
          y2={y}
          strokeWidth={1.5 + Math.abs(item.value) * 5}
          opacity={0.25 + item.confidence * 0.65}
        />
      ))}
      <circle className="ci-social-center" cx={centerX} cy={centerY} r="38" />
      {identityGraph.character_avatar_url ? (
        <image
          href={identityGraph.character_avatar_url}
          x={centerX - 37}
          y={centerY - 37}
          width="74"
          height="74"
          preserveAspectRatio="xMidYMid slice"
          clipPath="url(#ci-social-center-avatar)"
        />
      ) : null}
      <text className="ci-social-center-label" x={centerX} y={centerY + 55} textAnchor="middle">{identityGraph.character_display_name.slice(0, 18)}</text>
      {positions.map(({ item, index, x, y }) => {
        const nodeRadius = 22 + Math.abs(item.value) * 7;
        return (
          <g key={item.subject_key}>
            <circle className="ci-social-node" cx={x} cy={y} r={nodeRadius} />
            {item.avatar_url ? (
              <image
                href={item.avatar_url}
                x={x - nodeRadius + 1}
                y={y - nodeRadius + 1}
                width={(nodeRadius - 1) * 2}
                height={(nodeRadius - 1) * 2}
                preserveAspectRatio="xMidYMid slice"
                clipPath={`url(#ci-social-avatar-${index})`}
              />
            ) : null}
            <text className="ci-social-node-label" x={x} y={y + nodeRadius + 14} textAnchor="middle">{item.label.slice(0, 16)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function ConversationIntelligenceInspector({ cards, profile, catalog, zh }: Props) {
  const [tab, setTab] = useState<IntelligenceTab>("overview");
  const [characterId, setCharacterId] = useState(cards[0]?.id ?? "");
  const [channelId, setChannelId] = useState(catalog?.channels[0]?.id ?? "");
  const [character, setCharacter] = useState<CharacterIntelligenceSnapshot | null>(null);
  const [overview, setOverview] = useState<TopicOverview | null>(null);
  const [topics, setTopics] = useState<TopicTimelineSnapshot | null>(null);
  const [decisions, setDecisions] = useState<TopicDecisionTimeline | null>(null);
  const [memories, setMemories] = useState<CharacterMemorySnapshot | null>(null);
  const [coreMemories, setCoreMemories] = useState<CoreMemorySnapshot | null>(null);
  const [history, setHistory] = useState<CharacterMindHistory | null>(null);
  const [interests, setInterests] = useState<CurrentInterestSnapshot | null>(null);
  const [social, setSocial] = useState<SocialEgoGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [newCore, setNewCore] = useState("");
  const [coreScope, setCoreScope] = useState<"character_global" | "character_server">("character_server");

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

  const loadServer = async () => {
    if (!profile.connection_id || !profile.guild_id) return;
    setOverview(await conversationIntelligenceApi.overview(profile.connection_id, profile.guild_id));
  };
  const loadChannel = async () => {
    if (!channelId) { setTopics(null); setDecisions(null); return; }
    const input = { connectionId: profile.connection_id, guildId: profile.guild_id, channelId };
    const [topicValue, decisionValue] = await Promise.all([
      conversationIntelligenceApi.topics(input),
      conversationIntelligenceApi.topicDecisions(input)
    ]);
    setTopics(topicValue);
    setDecisions(decisionValue);
  };
  const loadCharacter = async () => {
    if (!characterId) return;
    const [stateValue, memoryValue, coreValue, historyValue, interestValue, socialValue] = await Promise.all([
      conversationIntelligenceApi.character(characterId),
      conversationIntelligenceApi.memories(characterId, profile.connection_id, profile.guild_id),
      conversationIntelligenceApi.coreMemories(characterId, profile.connection_id, profile.guild_id),
      conversationIntelligenceApi.characterHistory(characterId, profile.connection_id, profile.guild_id),
      conversationIntelligenceApi.interests(characterId, profile.connection_id, profile.guild_id),
      conversationIntelligenceApi.socialGraph(characterId, profile.connection_id, profile.guild_id)
    ]);
    setCharacter(stateValue);
    setMemories(memoryValue);
    setCoreMemories(coreValue);
    setHistory(historyValue);
    setInterests(interestValue);
    setSocial(socialValue);
  };

  useEffect(() => {
    let active = true;
    setError("");
    void loadServer().catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [profile.connection_id, profile.guild_id]);
  useEffect(() => {
    let active = true;
    setError("");
    void loadChannel().catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [channelId, profile.connection_id, profile.guild_id]);
  useEffect(() => {
    let active = true;
    setError("");
    void loadCharacter().catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [characterId, profile.connection_id, profile.guild_id]);

  const currentTopic = topics?.items.find((item) => item.id === topics.current_topic_id) ?? null;
  const nowStates = (character?.items ?? []).filter((item) => nowStateTypes.has(item.state_type));
  const developingStates = (character?.items ?? []).filter((item) => developingStateTypes.has(item.state_type));
  const relationshipStates = (character?.items ?? []).filter((item) => item.state_type === "relationship");
  const socialItems = (social?.items ?? []) as SocialIdentityNeighbor[];

  const runAction = async (action: () => Promise<unknown>, reload: () => Promise<void>, message: string) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await reload(); setNotice(message); }
    catch (reason: unknown) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const deleteTopic = async (topicId: string) => {
    setBusy(true); setError(""); setNotice("");
    try {
      const impact = await conversationIntelligenceApi.topicDeleteImpact(topicId);
      const prompt = zh
        ? `删除这个 Topic 的派生 intelligence？会影响 ${impact.total_derived_records} 条记录；原始 Discord 消息不会删除。`
        : `Delete this Topic's derived intelligence? ${impact.total_derived_records} derived records are affected; raw Discord messages stay intact.`;
      if (!window.confirm(prompt)) return;
      await conversationIntelligenceApi.deleteTopicDerived(topicId);
      await Promise.all([loadChannel(), loadServer(), loadCharacter()]);
      setNotice(zh ? "Topic 派生数据已清理。" : "Topic-derived intelligence was removed.");
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const tabs: Array<{ key: IntelligenceTab; en: string; cn: string }> = [
    { key: "overview", en: "Overview", cn: "总览" },
    { key: "topics", en: "Topics", cn: "Topic" },
    { key: "memories", en: "Memories", cn: "记忆" },
    { key: "mind", en: "Character Mind", cn: "角色心智" },
    { key: "social", en: "Social Graph", cn: "关系图" },
    { key: "hygiene", en: "Data Hygiene", cn: "数据清理" }
  ];

  return (
    <section className="conversation-intelligence-inspector ci-control-plane">
      <header className="conversation-intelligence-head paper-sheet ci-control-head">
        <div>
          <StickyLabel variant="link">CONVERSATION INTELLIGENCE</StickyLabel>
          <h2>{zh ? "Conversation Intelligence 控制面" : "Conversation Intelligence Control Plane"}</h2>
          <p>{zh ? "观察 Topic、分层 Memory、角色心智与关系证据；清理操作只影响派生 intelligence。" : "Observe Topics, layered Memory, Character Mind, and relationship evidence. Hygiene actions target derived intelligence only."}</p>
        </div>
        <div className="ci-head-selectors">
          <Select value={characterId} onChange={(event) => setCharacterId(event.currentTarget.value)}>{cards.map((card) => <option key={card.id} value={card.id}>{card.display_name}</option>)}</Select>
          <Select value={channelId} onChange={(event) => setChannelId(event.currentTarget.value)}>{channels.map((channel) => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}</Select>
        </div>
      </header>

      <PageFlagGroup className="ci-index-tabs" orientation="horizontal" label="Conversation Intelligence sections">
        {tabs.map((item, index) => <PageFlag key={item.key} tone={tabTones[index]} active={tab === item.key} onClick={() => setTab(item.key)}>{zh ? item.cn : item.en}</PageFlag>)}
      </PageFlagGroup>

      {error && <Toast tone="danger" title={zh ? "Conversation Intelligence 错误" : "Conversation Intelligence error"}>{error}</Toast>}
      {notice && <Toast tone="success" title={zh ? "已完成" : "Completed"}>{notice}</Toast>}
      {busy && <div className="ci-busy"><Spinner size="sm" label={zh ? "更新中" : "Updating"} /></div>}

      {tab === "overview" && (
        <div className="ci-overview-grid">
          <InspectorSection eyebrow="SERVER / TOPIC HEALTH" title={profile.guild_name || profile.name}>
            <div className="ci-stat-grid">
              {[
                [zh ? "Active" : "Active", overview?.active ?? 0],
                [zh ? "Stale Active" : "Stale active", overview?.stale_active ?? 0],
                [zh ? "Cooling" : "Cooling", overview?.cooling ?? 0],
                [zh ? "Closed" : "Closed", overview?.closed ?? 0],
                [zh ? "Archived" : "Archived", overview?.archived ?? 0],
                [zh ? "Channels" : "Channels", overview?.channel_count ?? 0]
              ].map(([label, value]) => <PaperCard className="ci-stat" key={String(label)}><span>{label}</span><strong>{value}</strong></PaperCard>)}
            </div>
            {(overview?.stale_active ?? 0) > 0 && <StickyNote variant="warning"><strong>{zh ? "发现 stale active Topic" : "Stale active Topics detected"}</strong><p>{zh ? "打开 Topics 查看 lifecycle 与 switch decision。" : "Open Topics to inspect lifecycle and switch decisions."}</p></StickyNote>}
          </InspectorSection>
          <InspectorSection eyebrow="CHARACTER / MEMORY" title={selectedCard?.display_name ?? "—"}>
            <div className="ci-stat-grid">
              <PaperCard className="ci-stat"><span>Core Memory</span><strong>{coreMemories?.items.length ?? 0}</strong></PaperCard>
              <PaperCard className="ci-stat"><span>Synthesized</span><strong>{memories?.items.length ?? 0}</strong></PaperCard>
              <PaperCard className="ci-stat"><span>Interests</span><strong>{interests?.items.length ?? 0}</strong></PaperCard>
              <PaperCard className="ci-stat"><span>Relationships</span><strong>{social?.items.length ?? 0}</strong></PaperCard>
            </div>
            <StickyNote variant="character"><strong>{zh ? "分层原则" : "Layering"}</strong><p>{zh ? "Core 是明确保存的 durable memory；Synthesized 是后台整理；Episode history 只允许角色检索自己实际看过的内容。" : "Core is explicit durable memory; Synthesized is background-curated; episodic history is restricted to content the Character actually perceived."}</p></StickyNote>
          </InspectorSection>
        </div>
      )}

      {tab === "topics" && (
        <div className="ci-two-column">
          <InspectorSection eyebrow="CURRENT / LIFECYCLE" title={zh ? "Topic 时间线" : "Topic timeline"}>
            {currentTopic ? <TopicNote topic={currentTopic.topic_label || "Untitled"} participants={`${currentTopic.message_count} messages · v${currentTopic.capsule_version}`} status={currentTopic.status}><p>{currentTopic.summary}</p></TopicNote> : <EmptyState title={zh ? "没有 active Topic" : "No active Topic"} />}
            <div className="ci-topic-list">
              {(topics?.items ?? []).map((topic) => <PaperCard key={topic.id} className="ci-topic-card"><div className="ci-card-head"><div><StickyLabel variant={topic.status === "active" ? "success" : "neutral"}>{topic.status}</StickyLabel><strong>{topic.topic_label || "Untitled"}</strong></div><div className="ci-actions"><Button size="sm" variant="ghost" disabled={busy || topic.status === "archived"} onClick={() => void runAction(() => conversationIntelligenceApi.archiveTopic(topic.id), loadChannel, zh ? "Topic 已 archive。" : "Topic archived.")}>{zh ? "Archive" : "Archive"}</Button><Button size="sm" variant="danger" disabled={busy} onClick={() => void deleteTopic(topic.id)}>{zh ? "清理" : "Clean"}</Button></div></div><p>{topic.summary}</p><small>{new Date(topic.last_active_at).toLocaleString()} · {topic.message_count} messages</small></PaperCard>)}
            </div>
          </InspectorSection>
          <InspectorSection eyebrow="DECISION TRACE" title={zh ? "为什么切换 / 延续" : "Why it switched or continued"}>
            <div className="ci-decision-list">
              {(decisions?.items ?? []).map((item) => <PaperCard key={item.id} className="ci-decision-card"><div className="ci-decision-route"><strong>{item.from_topic_label || "∅"}</strong><span>→ {item.decision} →</span><strong>{item.to_topic_label || "∅"}</strong></div><p>{item.reason}</p><div className="ci-score-grid"><span>dense <b>{item.dense_score.toFixed(3)}</b></span><span>sparse <b>{item.sparse_score.toFixed(3)}</b></span><span>continue <b>{item.continuation_score.toFixed(3)}</b></span><span>switch <b>{item.switch_score.toFixed(3)}</b></span></div><small>{new Date(item.created_at).toLocaleString()} · idle {formatAge(item.idle_seconds, zh)}</small></PaperCard>)}
              {(decisions?.items.length ?? 0) === 0 && <EmptyState title={zh ? "还没有 decision trace" : "No decision trace yet"} />}
            </div>
          </InspectorSection>
        </div>
      )}

      {tab === "memories" && (
        <div className="ci-two-column">
          <InspectorSection eyebrow="SAVED / CORE" title={zh ? "明确保存的记忆" : "Explicit Core Memory"}>
            <StickyNote variant="memory"><p>{zh ? "Core Memory 不会被后台 synthesis 自动覆写；可调整 priority、archive 或删除。" : "Core Memory is user-controlled and is not overwritten by background synthesis."}</p></StickyNote>
            <div className="ci-core-composer"><Textarea value={newCore} onChange={(event) => setNewCore(event.currentTarget.value)} placeholder={zh ? "写入一条需要角色长期记住的事实或偏好…" : "Write a fact or preference this Character should remember durably…"} /><div><Select value={coreScope} onChange={(event) => setCoreScope(event.currentTarget.value as "character_global" | "character_server")}><option value="character_server">Server</option><option value="character_global">Global</option></Select><Button variant="primary" disabled={!newCore.trim() || busy} onClick={() => void runAction(async () => { await conversationIntelligenceApi.createCoreMemory(characterId, { content: newCore, scopeType: coreScope, connectionId: coreScope === "character_server" ? profile.connection_id : "", guildId: coreScope === "character_server" ? profile.guild_id : "", priority: 0.85 }); setNewCore(""); }, loadCharacter, zh ? "Core Memory 已保存。" : "Core Memory saved.")}>{zh ? "保存" : "Save"}</Button></div></div>
            <div className="ci-memory-list">{(coreMemories?.items ?? []).map((item) => <PaperCard key={item.id} className="ci-memory-card"><div className="ci-card-head"><div><StickyLabel variant="memory">CORE</StickyLabel><strong>{item.memory_type}</strong></div><strong>{Math.round(item.priority * 100)}%</strong></div><p>{item.content}</p><small>{item.scope_type} · used {item.use_count} · {new Date(item.updated_at).toLocaleString()}</small><div className="ci-actions"><Button size="sm" variant="ghost" onClick={() => void runAction(() => conversationIntelligenceApi.updateCoreMemory(item.id, { status: "archived" }), loadCharacter, zh ? "Core Memory 已 archive。" : "Core Memory archived.")}>Archive</Button><Button size="sm" variant="danger" onClick={() => { if (window.confirm(zh ? "删除这条 Core Memory？" : "Delete this Core Memory?")) void runAction(() => conversationIntelligenceApi.deleteCoreMemory(item.id), loadCharacter, zh ? "Core Memory 已删除。" : "Core Memory deleted."); }}>Delete</Button></div></PaperCard>)}</div>
          </InspectorSection>
          <InspectorSection eyebrow="BACKGROUND / SYNTHESIZED" title={zh ? "后台整理的记忆" : "Background Synthesized Memory"}>
            <div className="ci-memory-list">{(memories?.items ?? []).map((item) => <PaperCard key={item.id} className="ci-memory-card"><div className="ci-card-head"><div><StickyLabel variant="vision">SYNTHESIZED</StickyLabel><strong>{item.memory_type}</strong></div><span>{item.status}</span></div><p>{item.content}</p><div className="ci-score-grid"><span>confidence <b>{item.confidence.toFixed(2)}</b></span><span>importance <b>{item.importance.toFixed(2)}</b></span><span>uses <b>{item.use_count}</b></span><span>evidence <b>{item.provenance_episode_ids.length}</b></span></div><div className="ci-actions"><Button size="sm" variant="primary" onClick={() => void runAction(() => conversationIntelligenceApi.promoteMemory(item.id), loadCharacter, zh ? "已提升为 Core Memory。" : "Promoted to Core Memory.")}>{zh ? "提升到 Core" : "Promote to Core"}</Button><Button size="sm" variant="ghost" onClick={() => void runAction(() => conversationIntelligenceApi.invalidateMemory(item.id), loadCharacter, zh ? "Memory 已 invalidated。" : "Memory invalidated.")}>Invalidate</Button><Button size="sm" variant="danger" onClick={() => { if (window.confirm(zh ? "永久删除这条 synthesized Memory？" : "Permanently delete this synthesized Memory?")) void runAction(() => conversationIntelligenceApi.deleteMemory(item.id), loadCharacter, zh ? "Memory 已删除。" : "Memory deleted."); }}>Delete</Button></div></PaperCard>)}</div>
          </InspectorSection>
        </div>
      )}

      {tab === "mind" && (
        <div className="ci-mind-layout">
          <InspectorSection eyebrow="NOW / FAST DECAY" title={zh ? "当前状态" : "Right now"}><div className="ci-state-grid">{nowStates.map((item) => <StateCard key={item.id} item={item} zh={zh} />)}{nowStates.length === 0 && <EmptyState title={zh ? "暂无短期状态" : "No short-lived state yet"} />}</div></InspectorSection>
          <InspectorSection eyebrow="CURRENT INTERESTS" title={zh ? "正在发展的兴趣" : "Developing interests"}><div className="ci-interest-list">{(interests?.items ?? []).map((item) => <PaperCard key={item.subject_key} className="ci-interest-card"><div><strong>{item.subject_label}</strong><span>{trendGlyph(item.trend)} {item.trend}</span></div><div className="ci-strength-track"><i style={{ width: `${percent(item.value)}%` }} /></div><small>{formatValue(item.value)} · confidence {item.confidence.toFixed(2)} · {item.evidence_count} evidence</small></PaperCard>)}{(interests?.items.length ?? 0) === 0 && <EmptyState title={zh ? "暂无兴趣 evidence" : "No interest evidence yet"} />}</div></InspectorSection>
          <InspectorSection eyebrow="DEVELOPING / SLOWER DECAY" title={zh ? "专长与立场" : "Expertise & stance"}><div className="ci-state-grid">{developingStates.filter((item) => item.state_type !== "interest").map((item) => <StateCard key={item.id} item={item} zh={zh} />)}</div></InspectorSection>
          <InspectorSection eyebrow="EVIDENCE HISTORY" title={zh ? "状态变化记录" : "State change history"}><div className="ci-history-list">{(history?.items ?? []).slice(0, 80).map((item) => <PaperCard key={item.id} className="ci-history-event"><div><strong>{stateLabel(item.state_type, zh)} · {item.subject_label}</strong><span>{formatValue(item.delta)} × {item.evidence_confidence.toFixed(2)}</span></div><p>{item.reason_code || item.source_type}</p><small>{formatValue(item.value_before)} → {formatValue(item.value_after)} · {new Date(item.recorded_at).toLocaleString()}</small></PaperCard>)}</div></InspectorSection>
        </div>
      )}

      {tab === "social" && (
        <div className="ci-two-column">
          <InspectorSection eyebrow="EGO GRAPH / SERVER" title={social?.character_display_name ?? selectedCard?.display_name ?? "—"}>{social && social.items.length ? <SocialGraphCanvas graph={social} /> : <EmptyState title={zh ? "暂无关系 evidence" : "No relationship evidence yet"} />}</InspectorSection>
          <InspectorSection eyebrow="RELATIONSHIP EVIDENCE" title={zh ? "邻接关系" : "Immediate relationships"}>
            <div className="ci-social-list">
              {socialItems.map((item) => <PaperCard key={item.subject_key} className="ci-social-row"><div className="ci-social-row__head"><div className="ci-social-identity">{item.avatar_url ? <img src={item.avatar_url} alt="" /> : <span className="ci-social-avatar-fallback">{item.label.slice(0, 1).toUpperCase()}</span>}<div><strong>{item.label}</strong>{item.discord_user_id && <small className="ci-social-user-id">{item.discord_user_id}</small>}</div></div><span>{item.subject_type === "character" ? "CHARACTER" : item.is_bot ? "BOT" : "USER"}</span></div><div className="ci-strength-track"><i style={{ width: `${percent(item.value)}%` }} /></div><small>{formatValue(item.value)} · confidence {item.confidence.toFixed(2)} · {item.evidence_count} evidence · {trendGlyph(item.trend)}</small></PaperCard>)}
            </div>
            <div className="ci-hidden-state-count">{relationshipStates.length} aggregate relationship state(s)</div>
          </InspectorSection>
        </div>
      )}

      {tab === "hygiene" && (
        <div className="ci-two-column">
          <InspectorSection eyebrow="CHARACTER / SERVER" title={zh ? "Memory 清理" : "Memory hygiene"}><StickyNote variant="warning"><p>{zh ? "这只清除当前 Character × Server 的 synthesized Memory，不删除 Core Memory，也不删除原始 Discord 对话。" : "This clears synthesized Memory for the selected Character × Server. Core Memory and raw Discord conversations are preserved."}</p></StickyNote><Button variant="danger" disabled={busy || !characterId} onClick={() => { if (window.confirm(zh ? "重置当前角色在这个 Server 的 synthesized Memory？" : "Reset synthesized Memory for this Character in this server?")) void runAction(() => conversationIntelligenceApi.resetCharacterMemories(characterId, profile.connection_id, profile.guild_id), loadCharacter, zh ? "角色 synthesized Memory 已重置。" : "Character synthesized Memory reset."); }}>{zh ? "Reset Synthesized Memory" : "Reset Synthesized Memory"}</Button></InspectorSection>
          <InspectorSection eyebrow="TOPIC / CHANNEL" title={zh ? "Topic 派生数据清理" : "Topic-derived hygiene"}><StickyNote variant="warning"><p>{zh ? "重置当前 Channel 的 Topic-derived intelligence；raw source messages 保留。单一 Topic 可在 Topics 页先 preview impact 再删除。" : "Reset Topic-derived intelligence for the selected channel. Raw source messages remain. Individual Topics can be previewed and cleaned from the Topics tab."}</p></StickyNote><Button variant="danger" disabled={busy || !channelId} onClick={() => { if (window.confirm(zh ? "重置这个 Channel 的 Topic 派生数据？" : "Reset Topic-derived intelligence for this channel?")) void runAction(() => conversationIntelligenceApi.resetTopicScope({ connectionId: profile.connection_id, guildId: profile.guild_id, channelId }), async () => { await Promise.all([loadChannel(), loadServer(), loadCharacter()]); }, zh ? "Channel Topic 派生数据已重置。" : "Channel Topic-derived intelligence reset."); }}>{zh ? "Reset Channel Topics" : "Reset Channel Topics"}</Button></InspectorSection>
          <InspectorSection eyebrow="SAFETY CONTRACT" title={zh ? "不会被删除的内容" : "What cleanup never deletes"}><div className="ci-contract-list"><span>✓ Raw Discord source messages/events</span><span>✓ Character Card authoritative persona</span><span>✓ Explicit Core Memory unless you delete it directly</span><span>✓ Provider credentials / deployment configuration</span></div></InspectorSection>
          <InspectorSection eyebrow="LAST RESULT" title={zh ? "清理结果说明" : "Cleanup semantics"}><p>{zh ? "所有 destructive action 都 owner-scoped，并通过审计记录。Topic 删除会连带清理 vector、Episode projection、Topic-local Memory、Wiki、Graph projection 与 checkpoint。" : "Destructive actions are owner-scoped and audited. Topic cleanup cascades through vectors, Episode projections, Topic-local Memory, Wiki, Graph projections, and checkpoints."}</p></InspectorSection>
        </div>
      )}
    </section>
  );
}