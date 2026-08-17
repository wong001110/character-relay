export interface LearnedStateProvenance {
  source_type: string;
  source_message_id: string;
  source_burst_id: string;
  reason_code: string;
  delta: number;
  confidence: number;
  recorded_at: string | null;
  contradiction: boolean;
}

export interface LearnedStateInspection {
  id: string;
  state_type: string;
  subject_type: string;
  subject_key: string;
  subject_label: string;
  stored_value: number;
  current_value: number;
  stored_confidence: number;
  current_confidence: number;
  positive_evidence_count: number;
  negative_evidence_count: number;
  contradiction_count: number;
  evidence_count: number;
  half_life_seconds: number;
  last_evidence_at: string;
  expires_at: string | null;
  provenance: LearnedStateProvenance[];
}

export interface CharacterIntelligenceSnapshot {
  character_card_id: string;
  character_display_name: string;
  items: LearnedStateInspection[];
}

export interface TopicInspection {
  id: string;
  topic_label: string;
  summary: string;
  keywords: string[];
  open_loops: string[];
  participants: string[];
  status: string;
  message_count: number;
  capsule_version: number;
  last_message_id: string;
  started_at: string;
  last_active_at: string;
  closed_at: string | null;
}

export interface TopicTimelineSnapshot {
  current_topic_id: string;
  items: TopicInspection[];
}

export interface TopicOverview {
  total: number;
  active: number;
  cooling: number;
  closed: number;
  archived: number;
  stale_active: number;
  channel_count: number;
}

export interface TopicDecision {
  id: string;
  message_id: string;
  from_topic_id: string;
  from_topic_label: string;
  to_topic_id: string;
  to_topic_label: string;
  decision: string;
  reason: string;
  dense_score: number;
  sparse_score: number;
  continuation_score: number;
  switch_score: number;
  candidate_dense_score: number;
  candidate_sparse_score: number;
  idle_seconds: number;
  created_at: string;
}

export interface TopicDecisionTimeline {
  items: TopicDecision[];
}

export interface MemoryInspection {
  id: string;
  character_card_id: string;
  connection_id: string;
  guild_id: string;
  scope_type: string;
  subject_user_id: string;
  topic_id: string;
  memory_type: string;
  content: string;
  confidence: number;
  importance: number;
  status: string;
  provenance_episode_ids: string[];
  source_message_ids: string[];
  supersedes_memory_id: string;
  use_count: number;
  valid_from: string | null;
  valid_to: string | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface CharacterMemorySnapshot {
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  guild_id: string;
  items: MemoryInspection[];
}

export interface CoreMemory {
  id: string;
  character_card_id: string;
  connection_id: string;
  guild_id: string;
  scope_type: string;
  subject_user_id: string;
  memory_type: string;
  content: string;
  priority: number;
  status: string;
  source_memory_id: string;
  source_message_id: string;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoreMemorySnapshot {
  character_card_id: string;
  items: CoreMemory[];
}

export interface TopicDeleteImpact {
  topic_id: string;
  topic_found: boolean;
  topics: number;
  episodes: number;
  memories: number;
  wiki_pages: number;
  authority_edges: number;
  checkpoints: number;
  learned_states: number;
  graph_nodes: number;
  graph_edges: number;
  semantic_vectors: number;
  total_derived_records: number;
  raw_source_messages_deleted: number;
}

export interface DerivedResetResult {
  topics: number;
  episodes: number;
  memories: number;
  wiki_pages: number;
  authority_edges: number;
  checkpoints: number;
  learned_states: number;
  graph_nodes: number;
  graph_edges: number;
  semantic_vectors: number;
  raw_source_messages_deleted: number;
}

export interface CharacterMindEvent {
  id: string;
  state_type: string;
  subject_type: string;
  subject_key: string;
  subject_label: string;
  delta: number;
  evidence_confidence: number;
  value_before: number;
  value_after: number;
  confidence_before: number;
  confidence_after: number;
  contradiction: boolean;
  source_type: string;
  source_message_id: string;
  source_burst_id: string;
  reason_code: string;
  channel_id: string;
  topic_id: string;
  recorded_at: string;
}

export interface CharacterMindHistory {
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  guild_id: string;
  items: CharacterMindEvent[];
}

export interface SocialNeighbor {
  subject_key: string;
  subject_type: "actor" | "character";
  label: string;
  character_card_id: string;
  value: number;
  confidence: number;
  evidence_count: number;
  last_evidence_at: string;
  trend: string;
}

export interface SocialEgoGraph {
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  guild_id: string;
  items: SocialNeighbor[];
}

export interface InterestState {
  subject_key: string;
  subject_type: string;
  subject_label: string;
  value: number;
  confidence: number;
  evidence_count: number;
  last_evidence_at: string;
  trend: string;
}

export interface CurrentInterestSnapshot {
  character_card_id: string;
  character_display_name: string;
  connection_id: string;
  guild_id: string;
  items: InterestState[];
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers
    }
  });
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") throw new Error(parsed.detail);
  } catch (reason) {
    if (reason instanceof Error && reason.message !== raw) throw reason;
  }
  throw new Error(raw || `Request failed with ${response.status}`);
}

function serverQuery(connectionId: string, guildId: string): URLSearchParams {
  return new URLSearchParams({ connection_id: connectionId, guild_id: guildId });
}

export const conversationIntelligenceApi = {
  character(characterCardId: string) {
    return request<CharacterIntelligenceSnapshot>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}`
    );
  },

  overview(connectionId: string, guildId: string) {
    return request<TopicOverview>(
      `/api/conversation-intelligence/overview?${serverQuery(connectionId, guildId)}`
    );
  },

  topics(input: {
    connectionId: string;
    guildId: string;
    channelId: string;
    threadId?: string;
  }) {
    const query = new URLSearchParams({
      connection_id: input.connectionId,
      guild_id: input.guildId,
      channel_id: input.channelId,
      thread_id: input.threadId ?? "",
      limit: "20"
    });
    return request<TopicTimelineSnapshot>(`/api/conversation-intelligence/topics?${query}`);
  },

  topicDecisions(input: {
    connectionId: string;
    guildId: string;
    channelId: string;
    threadId?: string;
  }) {
    const query = new URLSearchParams({
      connection_id: input.connectionId,
      guild_id: input.guildId,
      channel_id: input.channelId,
      thread_id: input.threadId ?? "",
      limit: "100"
    });
    return request<TopicDecisionTimeline>(
      `/api/conversation-intelligence/topic-decisions?${query}`
    );
  },

  topicDeleteImpact(topicId: string) {
    return request<TopicDeleteImpact>(
      `/api/conversation-intelligence/topics/${encodeURIComponent(topicId)}/delete-impact`
    );
  },

  archiveTopic(topicId: string) {
    return request<TopicInspection>(
      `/api/conversation-intelligence/topics/${encodeURIComponent(topicId)}/archive`,
      { method: "POST" }
    );
  },

  deleteTopicDerived(topicId: string) {
    return request<TopicDeleteImpact>(
      `/api/conversation-intelligence/topics/${encodeURIComponent(topicId)}/derived?confirm=true`,
      { method: "DELETE" }
    );
  },

  resetTopicScope(input: {
    connectionId: string;
    guildId: string;
    channelId: string;
    threadId?: string;
  }) {
    return request<DerivedResetResult>("/api/conversation-intelligence/topics/reset-scope", {
      method: "POST",
      body: JSON.stringify({
        connection_id: input.connectionId,
        guild_id: input.guildId,
        channel_id: input.channelId,
        thread_id: input.threadId ?? "",
        confirm: true
      })
    });
  },

  memories(characterCardId: string, connectionId: string, guildId: string) {
    return request<CharacterMemorySnapshot>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/memories?${serverQuery(connectionId, guildId)}`
    );
  },

  coreMemories(characterCardId: string, connectionId: string, guildId: string) {
    return request<CoreMemorySnapshot>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/core-memories?${serverQuery(connectionId, guildId)}`
    );
  },

  createCoreMemory(characterCardId: string, input: {
    content: string;
    scopeType: "character_global" | "character_server" | "character_user";
    connectionId?: string;
    guildId?: string;
    subjectUserId?: string;
    memoryType?: string;
    priority?: number;
  }) {
    return request<CoreMemory>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/core-memories`,
      {
        method: "POST",
        body: JSON.stringify({
          content: input.content,
          scope_type: input.scopeType,
          connection_id: input.connectionId ?? "",
          guild_id: input.guildId ?? "",
          subject_user_id: input.subjectUserId ?? "",
          memory_type: input.memoryType ?? "other",
          priority: input.priority ?? 0.75
        })
      }
    );
  },

  updateCoreMemory(memoryId: string, input: {
    content?: string;
    memoryType?: string;
    priority?: number;
    status?: "active" | "archived";
  }) {
    return request<CoreMemory>(
      `/api/conversation-intelligence/core-memories/${encodeURIComponent(memoryId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          content: input.content,
          memory_type: input.memoryType,
          priority: input.priority,
          status: input.status
        })
      }
    );
  },

  deleteCoreMemory(memoryId: string) {
    return request<{ deleted: boolean }>(
      `/api/conversation-intelligence/core-memories/${encodeURIComponent(memoryId)}`,
      { method: "DELETE" }
    );
  },

  promoteMemory(memoryId: string, priority = 0.85) {
    return request<CoreMemory>(
      `/api/conversation-intelligence/memories/${encodeURIComponent(memoryId)}/promote`,
      { method: "POST", body: JSON.stringify({ priority }) }
    );
  },

  invalidateMemory(memoryId: string) {
    return request<MemoryInspection>(
      `/api/conversation-intelligence/memories/${encodeURIComponent(memoryId)}/invalidate`,
      { method: "POST" }
    );
  },

  deleteMemory(memoryId: string) {
    return request<void>(
      `/api/conversation-intelligence/memories/${encodeURIComponent(memoryId)}?confirm=true`,
      { method: "DELETE" }
    );
  },

  resetCharacterMemories(characterCardId: string, connectionId: string, guildId: string) {
    return request<DerivedResetResult>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/memories/reset`,
      {
        method: "POST",
        body: JSON.stringify({
          connection_id: connectionId,
          guild_id: guildId,
          confirm: true
        })
      }
    );
  },

  characterHistory(characterCardId: string, connectionId: string, guildId: string) {
    return request<CharacterMindHistory>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/history?${serverQuery(connectionId, guildId)}`
    );
  },

  interests(characterCardId: string, connectionId: string, guildId: string) {
    return request<CurrentInterestSnapshot>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/interests?${serverQuery(connectionId, guildId)}`
    );
  },

  socialGraph(characterCardId: string, connectionId: string, guildId: string) {
    return request<SocialEgoGraph>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}/social-graph?${serverQuery(connectionId, guildId)}`
    );
  }
};
