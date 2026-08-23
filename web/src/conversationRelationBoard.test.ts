import { describe, expect, it } from "vitest";

import { relationActionLabel, relationParticipants } from "./conversationRelationBoard";
import type { MessageRelationObservation } from "./conversationStructureApi";

function relation(overrides: Partial<MessageRelationObservation> = {}): MessageRelationObservation {
  return {
    id: "relation-1",
    source_message_id: "message-source",
    source_author_id: "member-source",
    source_author_display_name: "Mina",
    relation_class: "interaction",
    relation_type: "REPLY_TO",
    target_ref_type: "message",
    target_ref: "message-target",
    target_author_id: "member-target",
    target_author_display_name: "Zhi",
    confidence: 1,
    source: "discord_explicit",
    evidence_refs: [],
    status: "resolved",
    supersedes_relation_id: "",
    created_at: "2026-08-23T12:00:00+00:00",
    ...overrides
  };
}

describe("Conversation Relation Board projection", () => {
  it("uses stored author snapshots rather than opaque message IDs", () => {
    expect(relationParticipants(relation(), false)).toEqual({ source: "Mina", target: "Zhi" });
    expect(relationActionLabel(relation(), false)).toBe("replied to");
  });

  it("does not guess historical authors when no snapshot exists", () => {
    expect(
      relationParticipants(
        relation({ source_author_display_name: "", target_author_display_name: "" }),
        true
      )
    ).toEqual({ source: "发送者未记录", target: "被回复者未记录" });
  });
});
