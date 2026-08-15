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

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
  if (response.ok) return response.json() as Promise<T>;
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") throw new Error(parsed.detail);
  } catch (reason) {
    if (reason instanceof Error && reason.message !== raw) throw reason;
  }
  throw new Error(raw || `Request failed with ${response.status}`);
}

export const conversationIntelligenceApi = {
  character(characterCardId: string) {
    return request<CharacterIntelligenceSnapshot>(
      `/api/conversation-intelligence/characters/${encodeURIComponent(characterCardId)}`
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
  }
};
