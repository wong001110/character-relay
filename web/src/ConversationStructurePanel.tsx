import { useEffect, useMemo, useState } from "react";

import type { CharacterDeployment } from "./deploymentApi";
import {
  loadConversationStructurePage,
  type ConversationCollection,
  type ConversationStructureView
} from "./conversationStructureApi";
import { EPISODE_BOARD_PAGE_SIZE, groupEpisodesForBoard, episodeDisplayTitle } from "./conversationEpisodeBoard";
import {
  RELATION_BOARD_PAGE_SIZE,
  relationActionLabel,
  relationParticipants
} from "./conversationRelationBoard";
import { pageCount, pageItems } from "./conversationPagination";
import {
  buildConversationThreadMap,
  segmentDisplaySummary,
  THREAD_MAP_PAGE_SIZE,
  THREAD_SEGMENT_PAGE_SIZE,
  threadDisplaySummary,
  threadDisplayTitle
} from "./conversationThreadMap";
import { PaperDrawer } from "./NotebookUI";
import { Pagination } from "./Pagination";
import "./conversation-structure.css";

interface Props {
  deployments: CharacterDeployment[];
  zh: boolean;
  fixture?: ConversationStructureView;
}

type NotebookTab =
  | "threads"
  | "relations"
  | "episodes"
  | "entities"
  | "beliefs"
  | "social";

interface CursorState {
  page: number;
  cursor: string | null;
  nextCursor: string | null;
  hasMore: boolean;
  paged: boolean;
  history: Array<string | null>;
}

const conversationCollections: ConversationCollection[] = [
  "threads",
  "segments",
  "relations",
  "episodes",
  "entities",
  "knowledge_gaps",
  "beliefs",
  "social_events",
  "impressions"
];

function initialCursorState(): CursorState {
  return { page: 1, cursor: null, nextCursor: null, hasMore: false, paged: false, history: [null] };
}

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

export function ConversationStructurePanel({ deployments, zh, fixture }: Props) {
  const [deploymentId, setDeploymentId] = useState("");
  const [tab, setTab] = useState<NotebookTab>("threads");
  const [value, setValue] = useState<ConversationStructureView | null>(fixture ?? null);
  const [cursorState, setCursorState] = useState<Record<ConversationCollection, CursorState>>(() =>
    Object.fromEntries(conversationCollections.map((item) => [item, initialCursorState()])) as Record<ConversationCollection, CursorState>
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [selectedRelationId, setSelectedRelationId] = useState<string | null>(null);
  const [fragmentsOpen, setFragmentsOpen] = useState(false);
  const [episodePage, setEpisodePage] = useState(1);
  const [episodeFragmentPage, setEpisodeFragmentPage] = useState(1);
  const [relationPage, setRelationPage] = useState(1);
  const [entityPage, setEntityPage] = useState(1);
  const [knowledgeGapPage, setKnowledgeGapPage] = useState(1);
  const [beliefPage, setBeliefPage] = useState(1);
  const [socialEventPage, setSocialEventPage] = useState(1);
  const [impressionPage, setImpressionPage] = useState(1);
  const [threadPage, setThreadPage] = useState(1);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [segmentPage, setSegmentPage] = useState(1);
  const [threadFragmentsOpen, setThreadFragmentsOpen] = useState(false);
  const [threadFragmentPage, setThreadFragmentPage] = useState(1);

  useEffect(() => {
    if (deploymentId && deployments.some((item) => item.id === deploymentId)) return;
    setDeploymentId(deployments[0]?.id ?? "");
  }, [deploymentId, deployments]);

  const deployment = useMemo(
    () => deployments.find((item) => item.id === deploymentId),
    [deploymentId, deployments]
  );

  async function load(targetId = deploymentId) {
    if (fixture) {
      setValue(fixture);
      setError("");
      return;
    }
    if (!targetId) {
      setValue(null);
      return;
    }
    try {
      setLoading(true);
      const next = await loadConversationStructurePage(targetId, { limit: 12 });
      setValue(next);
      setCursorState(
        Object.fromEntries(
          conversationCollections.map((collection) => {
            const page = next.pages[collection];
            return [collection, {
              page: 1,
              cursor: null,
              nextCursor: page.next_cursor,
              hasMore: page.has_more,
              paged: page.paged,
              history: [null]
            } satisfies CursorState];
          })
        ) as Record<ConversationCollection, CursorState>
      );
      setThreadPage(1);
      setEpisodePage(1);
      setEpisodeFragmentPage(1);
      setRelationPage(1);
      setEntityPage(1);
      setKnowledgeGapPage(1);
      setBeliefPage(1);
      setSocialEventPage(1);
      setImpressionPage(1);
      setError("");
    } catch (reason) {
      setValue(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!fixture) void load(deploymentId);
  }, [deploymentId, fixture]);

  async function loadCollectionPage(collection: ConversationCollection, page: number) {
    const state = cursorState[collection];
    if (!state.paged) return;
    if (page < 1 || (page > state.page && !state.hasMore)) return;
    const cursor = page === state.page
      ? state.cursor
      : page > state.page
        ? state.nextCursor
        : state.history[page - 1] ?? null;
    if (page > state.page && !cursor) return;
    try {
      setLoading(true);
      setError("");
      const next = await loadConversationStructurePage(deploymentId, {
        collection,
        cursor,
        limit: 12
      });
      setValue((current) => current ? {
        ...current,
        [collection]: next[collection]
      } : next);
      setCursorState((current) => {
        const previous = current[collection];
        const history = page > previous.page
          ? [...previous.history, cursor]
          : previous.history.slice(0, page);
        return {
          ...current,
          [collection]: {
            page,
            cursor,
            nextCursor: next.pages[collection].next_cursor,
            hasMore: next.pages[collection].has_more,
            paged: next.pages[collection].paged,
            history
          }
        };
      });
      if (collection === "threads") setThreadPage(page);
      if (collection === "relations") setRelationPage(page);
      if (collection === "episodes") setEpisodePage(page);
      if (collection === "entities") setEntityPage(page);
      if (collection === "knowledge_gaps") setKnowledgeGapPage(page);
      if (collection === "beliefs") setBeliefPage(page);
      if (collection === "social_events") setSocialEventPage(page);
      if (collection === "impressions") setImpressionPage(page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function changeCollectionPage(collection: ConversationCollection, page: number) {
    if (fixture) return;
    void loadCollectionPage(collection, page);
  }

  const tabs: Array<{ key: NotebookTab; en: string; zh: string; count: number }> = [
    {
      key: "threads",
      en: "Threads",
      zh: "对话线",
      count: value?.threads.length ?? 0
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
  const episodeGroups = useMemo(
    () => (value ? groupEpisodesForBoard(value.episodes) : { primary: [], fragments: [] }),
    [value]
  );
  const selectedEpisode = value?.episodes.find((episode) => episode.id === selectedEpisodeId) ?? null;
  const selectedRelation = value?.relations.find((relation) => relation.id === selectedRelationId) ?? null;
  const episodePages = cursorState.episodes.paged
    ? (cursorState.episodes.hasMore ? cursorState.episodes.page + 1 : cursorState.episodes.page)
    : pageCount(episodeGroups.primary.length, EPISODE_BOARD_PAGE_SIZE);
  const visibleEpisodes = useMemo(
    () => cursorState.episodes.paged ? episodeGroups.primary : pageItems(episodeGroups.primary, episodePage, EPISODE_BOARD_PAGE_SIZE),
    [cursorState.episodes.paged, episodeGroups.primary, episodePage]
  );
  const episodeFragmentPages = pageCount(episodeGroups.fragments.length, EPISODE_BOARD_PAGE_SIZE);
  const visibleEpisodeFragments = useMemo(
    () => pageItems(episodeGroups.fragments, episodeFragmentPage, EPISODE_BOARD_PAGE_SIZE),
    [episodeGroups.fragments, episodeFragmentPage]
  );
  const relationPages = cursorState.relations.paged
    ? (cursorState.relations.hasMore ? cursorState.relations.page + 1 : cursorState.relations.page)
    : pageCount(value?.relations.length ?? 0, RELATION_BOARD_PAGE_SIZE);
  const visibleRelations = useMemo(
    () => cursorState.relations.paged ? (value?.relations ?? []) : pageItems(value?.relations ?? [], relationPage, RELATION_BOARD_PAGE_SIZE),
    [cursorState.relations.paged, value?.relations, relationPage]
  );
  const evidencePageSize = 12;
  const entityPages = cursorState.entities.paged
    ? (cursorState.entities.hasMore ? cursorState.entities.page + 1 : cursorState.entities.page)
    : pageCount(value?.entities.length ?? 0, evidencePageSize);
  const visibleEntities = useMemo(
    () => cursorState.entities.paged ? (value?.entities ?? []) : pageItems(value?.entities ?? [], entityPage, evidencePageSize),
    [cursorState.entities.paged, value?.entities, entityPage]
  );
  const knowledgeGapPages = cursorState.knowledge_gaps.paged
    ? (cursorState.knowledge_gaps.hasMore ? cursorState.knowledge_gaps.page + 1 : cursorState.knowledge_gaps.page)
    : pageCount(value?.knowledge_gaps.length ?? 0, evidencePageSize);
  const visibleKnowledgeGaps = useMemo(
    () => cursorState.knowledge_gaps.paged ? (value?.knowledge_gaps ?? []) : pageItems(value?.knowledge_gaps ?? [], knowledgeGapPage, evidencePageSize),
    [cursorState.knowledge_gaps.paged, value?.knowledge_gaps, knowledgeGapPage]
  );
  const beliefPages = cursorState.beliefs.paged
    ? (cursorState.beliefs.hasMore ? cursorState.beliefs.page + 1 : cursorState.beliefs.page)
    : pageCount(value?.beliefs.length ?? 0, evidencePageSize);
  const visibleBeliefs = useMemo(
    () => cursorState.beliefs.paged ? (value?.beliefs ?? []) : pageItems(value?.beliefs ?? [], beliefPage, evidencePageSize),
    [cursorState.beliefs.paged, value?.beliefs, beliefPage]
  );
  const socialEventPages = cursorState.social_events.paged
    ? (cursorState.social_events.hasMore ? cursorState.social_events.page + 1 : cursorState.social_events.page)
    : pageCount(value?.social_events.length ?? 0, evidencePageSize);
  const visibleSocialEvents = useMemo(
    () => cursorState.social_events.paged ? (value?.social_events ?? []) : pageItems(value?.social_events ?? [], socialEventPage, evidencePageSize),
    [cursorState.social_events.paged, value?.social_events, socialEventPage]
  );
  const impressionPages = cursorState.impressions.paged
    ? (cursorState.impressions.hasMore ? cursorState.impressions.page + 1 : cursorState.impressions.page)
    : pageCount(value?.impressions.length ?? 0, evidencePageSize);
  const visibleImpressions = useMemo(
    () => cursorState.impressions.paged ? (value?.impressions ?? []) : pageItems(value?.impressions ?? [], impressionPage, evidencePageSize),
    [cursorState.impressions.paged, value?.impressions, impressionPage]
  );
  const threadMap = useMemo(
    () => buildConversationThreadMap(value?.threads ?? [], value?.segments ?? []),
    [value?.segments, value?.threads]
  );
  const threadPages = cursorState.threads.paged
    ? (cursorState.threads.hasMore ? cursorState.threads.page + 1 : cursorState.threads.page)
    : pageCount(threadMap.threads.length, THREAD_MAP_PAGE_SIZE);
  const visibleThreads = useMemo(
    () => cursorState.threads.paged ? threadMap.threads : pageItems(threadMap.threads, threadPage, THREAD_MAP_PAGE_SIZE),
    [cursorState.threads.paged, threadMap.threads, threadPage]
  );
  const selectedThread = threadMap.threads.find((item) => item.thread.id === selectedThreadId) ?? null;
  const segmentPages = pageCount(selectedThread?.segments.length ?? 0, THREAD_SEGMENT_PAGE_SIZE);
  const visibleSegments = useMemo(
    () => pageItems(selectedThread?.segments ?? [], segmentPage, THREAD_SEGMENT_PAGE_SIZE),
    [selectedThread?.segments, segmentPage]
  );
  const threadFragmentPages = pageCount(threadMap.unresolvedSegments.length, THREAD_SEGMENT_PAGE_SIZE);
  const visibleThreadFragments = useMemo(
    () => pageItems(threadMap.unresolvedSegments, threadFragmentPage, THREAD_SEGMENT_PAGE_SIZE),
    [threadMap.unresolvedSegments, threadFragmentPage]
  );

  useEffect(() => {
    setSelectedThreadId(null);
    setSegmentPage(1);
    setThreadFragmentPage(1);
    setSelectedEpisodeId(null);
    setSelectedRelationId(null);
  }, [value]);

  useEffect(() => {
    setThreadPage((current) => Math.min(Math.max(1, current), threadPages));
  }, [threadPages]);

  useEffect(() => {
    if (visibleThreads.some((item) => item.thread.id === selectedThreadId)) return;
    setSelectedThreadId(visibleThreads[0]?.thread.id ?? null);
  }, [selectedThreadId, visibleThreads]);

  useEffect(() => {
    setSegmentPage((current) => Math.min(Math.max(1, current), segmentPages));
  }, [segmentPages, selectedThreadId]);

  useEffect(() => {
    setThreadFragmentPage((current) => Math.min(Math.max(1, current), threadFragmentPages));
  }, [threadFragmentPages]);

  useEffect(() => {
    setEpisodePage((current) => Math.min(Math.max(1, current), episodePages));
  }, [episodePages]);

  useEffect(() => {
    setEpisodeFragmentPage((current) => Math.min(Math.max(1, current), episodeFragmentPages));
  }, [episodeFragmentPages]);

  useEffect(() => {
    setRelationPage((current) => Math.min(Math.max(1, current), relationPages));
  }, [relationPages]);

  useEffect(() => {
    setEntityPage((current) => Math.min(Math.max(1, current), entityPages));
  }, [entityPages]);

  useEffect(() => {
    setKnowledgeGapPage((current) => Math.min(Math.max(1, current), knowledgeGapPages));
  }, [knowledgeGapPages]);

  useEffect(() => {
    setBeliefPage((current) => Math.min(Math.max(1, current), beliefPages));
  }, [beliefPages]);

  useEffect(() => {
    setSocialEventPage((current) => Math.min(Math.max(1, current), socialEventPages));
  }, [socialEventPages]);

  useEffect(() => {
    setImpressionPage((current) => Math.min(Math.max(1, current), impressionPages));
  }, [impressionPages]);

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
              ? "Conversation / Knowledge 是当前 Server 的共享解释投影；Social 记录仍只属于所选 Character Deployment。"
              : "Conversation and Knowledge are shared Server projections. Social records remain scoped to the selected Character Deployment."}
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
            <section className="conversation-thread-map" aria-label={zh ? "对话线地图" : "Conversation map"}>
              <aside className="conversation-thread-map-index">
                <header>
                  <div><span className="tape-label">CONVERSATION MAP</span><strong>{zh ? "活动 / 最近对话线" : "Active / recent threads"}</strong></div>
                  <small>{threadMap.threads.length} {zh ? "条" : "threads"}</small>
                </header>
                <div className="conversation-thread-list">
                  {visibleThreads.map(({ thread, segments }) => (
                    <button
                      type="button"
                      key={thread.id}
                      className={thread.id === selectedThreadId ? "is-selected" : ""}
                      aria-pressed={thread.id === selectedThreadId}
                      onClick={() => { setSelectedThreadId(thread.id); setSegmentPage(1); }}
                    >
                      <span>{thread.status}</span>
                      <strong>{threadDisplayTitle(thread)}</strong>
                      <small>{segments.length} {zh ? "段" : "segments"} · {stamp(thread.last_active_at, zh)}</small>
                    </button>
                  ))}
                  {threadMap.threads.length === 0 && <small>{zh ? "还没有 Conversation Thread。" : "No Conversation Threads yet."}</small>}
                </div>
                <Pagination
                  page={threadPage}
                  pages={threadPages}
                  total={threadMap.threads.length}
                  onPage={(nextPage) => {
                    if (cursorState.threads.paged) {
                      changeCollectionPage("threads", nextPage);
                    } else {
                      setThreadPage(nextPage);
                      setSelectedThreadId(pageItems(threadMap.threads, nextPage, THREAD_MAP_PAGE_SIZE)[0]?.thread.id ?? null);
                    }
                    setSegmentPage(1);
                  }}
                  disabled={loading}
                />
              </aside>

              <section className="conversation-thread-map-detail" aria-live="polite">
                {selectedThread ? (
                  <>
                    <header>
                      <div><span className="tape-label">SELECTED THREAD</span><strong>{threadDisplayTitle(selectedThread.thread)}</strong></div>
                      <span>{selectedThread.thread.status}</span>
                    </header>
                    <p>{threadDisplaySummary(selectedThread.thread)}</p>
                    <dl>
                      <div><dt>{zh ? "参与者" : "Participants"}</dt><dd>{selectedThread.thread.participant_ids.length}</dd></div>
                      <div><dt>{zh ? "关联实体" : "Active entities"}</dt><dd>{selectedThread.thread.active_entity_ids.length}</dd></div>
                      <div><dt>{zh ? "关联片段" : "Resolved segments"}</dt><dd>{selectedThread.segments.length}</dd></div>
                      <div><dt>{zh ? "最近活动" : "Last active"}</dt><dd>{stamp(selectedThread.thread.last_active_at, zh)}</dd></div>
                    </dl>
                    <section className="conversation-thread-segments">
                      <header><strong>{zh ? "关联片段" : "Associated segments"}</strong><small>{selectedThread.segments.length} {zh ? "条" : "items"}</small></header>
                      <div className="conversation-segment-list">
                        {visibleSegments.map((segment) => (
                          <article key={segment.id}>
                            <header><strong>{segment.kind}</strong><span>{segment.membership_relation}</span></header>
                            <p>{segment.summary ? segmentDisplaySummary(segment) : (zh ? "只有上下文，没有摘要" : "Context-only segment")}</p>
                            <small>{segment.message_ids.length} msg · {segment.source} · {confidence(segment.confidence)}</small>
                          </article>
                        ))}
                        {selectedThread.segments.length === 0 && <small>{zh ? "这个 Thread 暂时没有已归属的 Segment。" : "No resolved Segments are attached to this Thread yet."}</small>}
                      </div>
                      <Pagination page={segmentPage} pages={segmentPages} total={selectedThread.segments.length} onPage={setSegmentPage} />
                    </section>
                  </>
                ) : <small>{zh ? "选择一条 Conversation Thread 查看详情。" : "Select a Conversation Thread to inspect its detail."}</small>}
              </section>

              {threadMap.unresolvedSegments.length > 0 && (
                <section className="conversation-thread-fragments">
                  <button type="button" aria-expanded={threadFragmentsOpen} onClick={() => setThreadFragmentsOpen((current) => !current)}>
                    {threadFragmentsOpen
                      ? (zh ? "收起未归属片段" : "Collapse unresolved inbox")
                      : (zh ? `展开 ${threadMap.unresolvedSegments.length} 条未归属片段` : `Expand ${threadMap.unresolvedSegments.length} unresolved fragments`)}
                  </button>
                  {threadFragmentsOpen && <>
                    <div className="conversation-segment-list">
                      {visibleThreadFragments.map((segment) => (
                        <article key={segment.id}>
                          <header><strong>{segment.kind}</strong><span>{segment.membership_relation}</span></header>
                          <p>{segment.summary ? segmentDisplaySummary(segment) : (zh ? "只有上下文，没有摘要" : "Context-only segment")}</p>
                          <small>{segment.message_ids.length} msg · {segment.source} · {confidence(segment.confidence)}</small>
                        </article>
                      ))}
                    </div>
                    <Pagination page={threadFragmentPage} pages={threadFragmentPages} total={threadMap.unresolvedSegments.length} onPage={setThreadFragmentPage} />
                  </>}
                </section>
              )}
            </section>
          )}

          {tab === "relations" && (
            <section className="conversation-relation-board" aria-label={zh ? "消息关系便利贴" : "Message relation board"}>
              <header className="conversation-relation-board-heading">
                <div><span className="tape-label">MESSAGE RELATIONS</span><strong>{zh ? "谁回复了谁" : "Who replied to whom"}</strong><small>{zh ? "便利贴使用保存的作者快照；旧记录缺少快照时会明确标注，绝不从 UID 猜测身份。" : "Notes use stored author snapshots. Older rows without a snapshot are labelled instead of guessing from an ID."}</small></div>
                <small>{value.relations.length} {zh ? "条关系" : "relations"}</small>
              </header>
              <div className="conversation-relation-note-grid">
                {visibleRelations.map((relation) => {
                  const participants = relationParticipants(relation, zh);
                  return (
                    <button type="button" key={relation.id} className="conversation-relation-note" onClick={() => setSelectedRelationId(relation.id)}>
                      <header><span>{relation.relation_type}</span><small>{relation.status}</small></header>
                      <strong>{participants.source}</strong>
                      <span className="conversation-relation-arrow">{relationActionLabel(relation, zh)} ↪</span>
                      <strong>{participants.target}</strong>
                      <small>{relation.relation_class} · {confidence(relation.confidence)} · {stamp(relation.created_at, zh)}</small>
                    </button>
                  );
                })}
                {value.relations.length === 0 && <small>{zh ? "还没有 Message Relation。" : "No Message Relations yet."}</small>}
              </div>
              <Pagination page={relationPage} pages={relationPages} total={value.relations.length} onPage={(page) => cursorState.relations.paged ? changeCollectionPage("relations", page) : setRelationPage(page)} disabled={loading} />
            </section>
          )}

          {tab === "episodes" && (
            <section className="conversation-episode-board" aria-label={zh ? "对话事件板" : "Conversation Board"}>
              <header className="conversation-episode-board-heading">
                <div><span className="tape-label">CONVERSATION BOARD</span><strong>{zh ? "对话事件便利贴" : "Conversation Episodes"}</strong><small>{zh ? "标题是为浏览而压缩的已存摘要；打开便利贴查看来源信息。" : "Titles are compact views of stored summaries; open a note for provenance."}</small></div>
                <small>{episodeGroups.primary.length} {zh ? "条事件" : "events"}</small>
              </header>
              <div className="conversation-episode-note-grid">
                {visibleEpisodes.map((episode) => (
                  <button type="button" key={episode.id} className="conversation-episode-note" onClick={() => setSelectedEpisodeId(episode.id)}>
                    <span className="conversation-episode-status">{episode.status}</span>
                    <strong>{episodeDisplayTitle(episode)}</strong>
                    <small>{episode.segment_ids.length} {zh ? "段" : "segments"} · {episode.source_message_ids.length} {zh ? "消息" : "messages"}</small>
                    <time dateTime={episode.ended_at}>{stamp(episode.ended_at, zh)}</time>
                  </button>
                ))}
                {episodeGroups.primary.length === 0 && <small>{zh ? "还没有可归档的 Episode。" : "No filed Episodes yet."}</small>}
              </div>
              <Pagination page={episodePage} pages={episodePages} total={episodeGroups.primary.length} onPage={(page) => cursorState.episodes.paged ? changeCollectionPage("episodes", page) : setEpisodePage(page)} disabled={loading} />
              {episodeGroups.fragments.length > 0 && (
                <section className="conversation-unresolved-fragments">
                  <button type="button" aria-expanded={fragmentsOpen} onClick={() => setFragmentsOpen((current) => !current)}>
                    {fragmentsOpen ? (zh ? "收起未归档片段" : "Collapse unresolved fragments") : (zh ? `展开 ${episodeGroups.fragments.length} 条未归档片段` : `Expand ${episodeGroups.fragments.length} unresolved fragments`)}
                  </button>
                  {fragmentsOpen && <><div>{visibleEpisodeFragments.map((episode) => <button type="button" key={episode.id} onClick={() => setSelectedEpisodeId(episode.id)}>{episodeDisplayTitle(episode, 58)} <small>{stamp(episode.ended_at, zh)}</small></button>)}</div><Pagination page={episodeFragmentPage} pages={episodeFragmentPages} total={episodeGroups.fragments.length} onPage={setEpisodeFragmentPage} /></>}
                </section>
              )}
            </section>
          )}

          {tab === "entities" && (
            <div className="conversation-structure-layout">
              <div>
                <span className="tape-label">ENTITY GROUNDING</span>
                <div className="conversation-evidence-grid">
                  {visibleEntities.map((entity) => (
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
                <Pagination page={entityPage} pages={entityPages} total={value.entities.length} onPage={(page) => cursorState.entities.paged ? changeCollectionPage("entities", page) : setEntityPage(page)} disabled={loading} />
              </div>
              <div>
                <span className="tape-label">KNOWLEDGE GAPS</span>
                <div className="conversation-evidence-grid">
                  {visibleKnowledgeGaps.map((gap) => (
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
              <Pagination page={knowledgeGapPage} pages={knowledgeGapPages} total={value.knowledge_gaps.length} onPage={(page) => cursorState.knowledge_gaps.paged ? changeCollectionPage("knowledge_gaps", page) : setKnowledgeGapPage(page)} disabled={loading} />
              </div>
            </div>
          )}

          {tab === "beliefs" && (
            <>
              <div className="conversation-evidence-grid">
                {visibleBeliefs.map((belief) => (
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
              <Pagination page={beliefPage} pages={beliefPages} total={value.beliefs.length} onPage={(page) => cursorState.beliefs.paged ? changeCollectionPage("beliefs", page) : setBeliefPage(page)} disabled={loading} />
            </>
          )}

          {tab === "social" && (
            <div className="conversation-structure-layout">
              <div>
                <span className="tape-label">SOCIAL EVENTS</span>
                <div className="conversation-evidence-grid">
                  {visibleSocialEvents.map((event) => (
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
              <Pagination page={socialEventPage} pages={socialEventPages} total={value.social_events.length} onPage={(page) => cursorState.social_events.paged ? changeCollectionPage("social_events", page) : setSocialEventPage(page)} disabled={loading} />
              </div>
              <div>
                <span className="tape-label">REVISABLE IMPRESSIONS</span>
                <div className="conversation-evidence-grid">
                  {visibleImpressions.map((impression) => (
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
              <Pagination page={impressionPage} pages={impressionPages} total={value.impressions.length} onPage={(page) => cursorState.impressions.paged ? changeCollectionPage("impressions", page) : setImpressionPage(page)} disabled={loading} />
              </div>
            </div>
          )}
        </>
      )}
      {selectedEpisode && (
        <PaperDrawer ariaLabel={zh ? "Episode 记录" : "Episode record"} onClose={() => setSelectedEpisodeId(null)} className="conversation-episode-drawer">
          <section className="conversation-episode-drawer-content">
            <span className="tape-label">STORED EPISODE SUMMARY</span>
            <h2>{episodeDisplayTitle(selectedEpisode)}</h2>
            <p>{selectedEpisode.summary || "—"}</p>
            <dl>
              <div><dt>{zh ? "状态" : "Status"}</dt><dd>{selectedEpisode.status}</dd></div>
              <div><dt>{zh ? "检查点" : "Checkpoint"}</dt><dd>{selectedEpisode.checkpoint_reason || "—"}</dd></div>
              <div><dt>{zh ? "线程" : "Thread"}</dt><dd>{shortRef(selectedEpisode.conversation_thread_id)}</dd></div>
              <div><dt>{zh ? "结束" : "Ended"}</dt><dd>{stamp(selectedEpisode.ended_at, zh)}</dd></div>
            </dl>
            <section><h3>{zh ? "已存事件摘要" : "Stored event notes"}</h3>{selectedEpisode.key_events.length ? <ul>{selectedEpisode.key_events.map((item, index) => <li key={`${selectedEpisode.id}-${index}`}>{item}</li>)}</ul> : <p>—</p>}</section>
            <section><h3>{zh ? "来源与范围" : "Provenance and scope"}</h3><p>{zh ? "此 API 仅提供 Episode 的来源 ID 与计数；这里不会把它伪装为原始消息内容。" : "This API provides Episode provenance IDs and counts only; it does not expose raw message content."}</p><dl><div><dt>Segments</dt><dd>{selectedEpisode.segment_ids.map(shortRef).join(" · ") || "—"}</dd></div><div><dt>{zh ? "消息 ID" : "Message IDs"}</dt><dd>{selectedEpisode.source_message_ids.map(shortRef).join(" · ") || "—"}</dd></div><div><dt>{zh ? "参与者 ID" : "Participant IDs"}</dt><dd>{selectedEpisode.participant_ids.map(shortRef).join(" · ") || "—"}</dd></div></dl></section>
          </section>
        </PaperDrawer>
      )}
      {selectedRelation && (() => {
        const participants = relationParticipants(selectedRelation, zh);
        return (
          <PaperDrawer ariaLabel={zh ? "消息关系记录" : "Message relation record"} onClose={() => setSelectedRelationId(null)} className="conversation-episode-drawer">
            <section className="conversation-episode-drawer-content">
              <span className="tape-label">STORED MESSAGE RELATION</span>
              <h2>{participants.source} {relationActionLabel(selectedRelation, zh)} {participants.target}</h2>
              <p>{zh ? "这是 Discord 显式关系的存档，不会展示原始消息内容。" : "This is a stored Discord relation; it does not expose raw message content."}</p>
              <dl>
                <div><dt>{zh ? "关系" : "Relation"}</dt><dd>{selectedRelation.relation_type} · {selectedRelation.status}</dd></div>
                <div><dt>{zh ? "置信度" : "Confidence"}</dt><dd>{confidence(selectedRelation.confidence)}</dd></div>
                <div><dt>{zh ? "发送者消息 ID" : "Source message ID"}</dt><dd>{shortRef(selectedRelation.source_message_id)}</dd></div>
                <div><dt>{zh ? "目标消息 ID" : "Target message ID"}</dt><dd>{selectedRelation.target_ref_type === "message" ? shortRef(selectedRelation.target_ref) : `${selectedRelation.target_ref_type}:${shortRef(selectedRelation.target_ref)}`}</dd></div>
                <div><dt>{zh ? "发送者快照" : "Sender snapshot"}</dt><dd>{selectedRelation.source_author_display_name || "—"}</dd></div>
                <div><dt>{zh ? "被回复者快照" : "Reply target snapshot"}</dt><dd>{selectedRelation.target_author_display_name || "—"}</dd></div>
              </dl>
              <section><h3>{zh ? "来源与范围" : "Provenance and scope"}</h3><p>{selectedRelation.evidence_refs.length} {zh ? "个证据引用" : "evidence references"} · {selectedRelation.source} · {stamp(selectedRelation.created_at, zh)}</p></section>
            </section>
          </PaperDrawer>
        );
      })()}
    </section>
  );
}
