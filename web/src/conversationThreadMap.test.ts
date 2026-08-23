import { describe, expect, it } from "vitest";

import {
  buildConversationThreadMap,
  segmentDisplaySummary,
  threadDisplaySummary,
  threadDisplayTitle
} from "./conversationThreadMap";
import { pageItems } from "./conversationPagination";
import type {
  ConversationSegmentObservation,
  ConversationThreadObservation
} from "./conversationStructureApi";

function thread(overrides: Partial<ConversationThreadObservation> = {}): ConversationThreadObservation {
  return {
    id: "thread-1",
    canonical_label: "A discussion line",
    anchor_summary: "The group compares two approaches.",
    working_summary: "They are deciding what to try next.",
    representative_segment_ids: [],
    participant_ids: [],
    active_entity_ids: [],
    status: "active",
    last_active_at: "2026-08-23T12:00:00+00:00",
    ...overrides
  };
}

function segment(overrides: Partial<ConversationSegmentObservation> = {}): ConversationSegmentObservation {
  return {
    id: "segment-1",
    burst_id: "burst-1",
    message_ids: [],
    participant_ids: [],
    kind: "discussion",
    summary: "A segment summary",
    thread_id: "thread-1",
    membership_relation: "belongs_to",
    membership_confidence: 0.9,
    confidence: 0.9,
    source: "deterministic",
    created_at: "2026-08-23T12:00:00+00:00",
    ...overrides
  };
}

describe("Conversation Thread Map projection", () => {
  it("groups only resolved memberships under known threads and keeps uncertainty separate", () => {
    const recent = thread({ id: "recent", last_active_at: "2026-08-23T13:00:00+00:00" });
    const older = thread({ id: "older", last_active_at: "2026-08-23T11:00:00+00:00" });
    const resolved = segment({ id: "resolved", thread_id: "older" });
    const unresolved = segment({ id: "unresolved", thread_id: "", membership_relation: "unresolved" });
    const staleReference = segment({ id: "stale", thread_id: "removed-thread" });

    const map = buildConversationThreadMap([older, recent], [resolved, unresolved, staleReference]);

    expect(map.threads.map((item) => item.thread.id)).toEqual(["recent", "older"]);
    expect(map.threads[1]?.segments).toEqual([resolved]);
    expect(map.unresolvedSegments).toEqual([unresolved, staleReference]);
  });

  it("makes thread labels safe and bounds local pagination", () => {
    expect(threadDisplayTitle(thread({ canonical_label: "https://example.test/post a useful thread" }))).toBe("link a useful thread");
    expect(threadDisplaySummary(thread({ working_summary: "x".repeat(200) }), 30)).toHaveLength(30);
    expect(segmentDisplaySummary(segment({ summary: "See https://example.test/very-long-link now" }))).toBe("See link now");
    expect(pageItems([1, 2, 3, 4, 5], 2, 2)).toEqual([3, 4]);
  });
});
