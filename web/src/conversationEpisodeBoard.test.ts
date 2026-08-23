import { describe, expect, it } from "vitest";

import { EPISODE_BOARD_PAGE_SIZE, episodeDisplayTitle, groupEpisodesForBoard } from "./conversationEpisodeBoard";
import type { EpisodeObservation } from "./conversationStructureApi";

function episode(overrides: Partial<EpisodeObservation> = {}): EpisodeObservation {
  return {
    id: "episode-123456789",
    conversation_thread_id: "thread-1",
    segment_ids: [],
    source_message_ids: [],
    participant_ids: [],
    entity_ids: [],
    media_refs: [],
    summary: "A stored event summary",
    key_events: [],
    status: "closed",
    checkpoint_reason: "checkpoint",
    ended_at: "2026-08-23T12:00:00+00:00",
    ...overrides
  };
}

describe("Conversation Episode Board projection", () => {
  it("never uses a raw URL as a note title and bounds display length", () => {
    expect(episodeDisplayTitle(episode({ summary: "https://example.test/a very long message" }))).toBe(
      "link very long message"
    );
    expect(episodeDisplayTitle(episode({ summary: "x".repeat(120) }), 20)).toHaveLength(20);
  });

  it("separates unresolved projections while leaving primary notes available to pagination", () => {
    const ordinary = Array.from({ length: 14 }, (_, index) => episode({ id: `episode-${index}` }));
    const unresolved = episode({ id: "fragment", conversation_thread_id: "", checkpoint_reason: "unresolved_segment" });

    const groups = groupEpisodesForBoard([...ordinary, unresolved]);

    expect(EPISODE_BOARD_PAGE_SIZE).toBe(12);
    expect(groups.primary).toHaveLength(14);
    expect(groups.fragments).toEqual([unresolved]);
  });
});
