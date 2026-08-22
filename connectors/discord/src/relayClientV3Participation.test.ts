import { afterEach, describe, expect, it, vi } from "vitest";

import { RelayClient } from "./relayClient.js";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function v3Response(overrides: Record<string, unknown> = {}): Response {
  return jsonResponse({
    resolver_version: "conversation-intelligence-v3",
    available: true,
    reason: "participation_planned",
    model: "e5",
    dimension: 1024,
    burst_id: "burst-1",
    burst_message_count: 2,
    analysis_chars: 20,
    candidates: [{
      deployment_id: "deployment-ann",
      character_card_id: "card-ann",
      eligible: true,
      deterministic_score: 0,
      minimum_score: 0,
      deterministic_signals: {},
      raw_e5_relevance: 0.81,
      profile_ready: true,
      semantic_points: 0,
      final_evidence_score: 0.81
    }],
    segmentation_used: true,
    segmentation_source: "reply_structure",
    conversation_segments: [{
      id: "segment-1",
      message_ids: ["message-1", "message-2"],
      participant_ids: ["user-1", "user-2"],
      kind: "conversation",
      summary: "A discussion.",
      conversation_thread_id: "thread-1",
      membership_relation: "belongs_to",
      membership_confidence: 0.9,
      confidence: 0.9,
      source: "structure"
    }],
    reply_targets: [{
      deployment_id: "deployment-ann",
      segment_id: "segment-1",
      conversation_thread_id: "thread-1",
      score: 0.9,
      reason: "direct_relevance",
      grounding_level: "context_only",
      context_sufficiency: "sufficient"
    }],
    speaker_plan: [{
      deployment_id: "deployment-ann",
      turn_role: "participant",
      reason: "direct_relevance",
      guidance: "Answer the question."
    }],
    speaker_plan_authoritative: true,
    participation_plan_reason: "direct_relevance",
    media_grounding_level: "context_only",
    media_grounding_reason: "no_media_dependency",
    context_sufficiency: { "deployment-ann": "sufficient" },
    utility_used: false,
    ...overrides
  });
}

describe("RelayClient v3 participation contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("forwards scope, burst provenance, and hard-gate candidates to v3", async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
      return v3Response();
    }));
    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    const result = await relay.resolveSmartParticipation({
      message: "first\nsecond",
      deployment_ids: ["deployment-ann"],
      guild_id: "guild-1",
      channel_id: "channel-1",
      thread_id: "thread-1",
      message_id: "message-2",
      author_id: "user-2",
      burst_id: "burst-1",
      burst_messages: [{
        message_id: "message-1", author_id: "user-1", author_display_name: "Alice",
        text: "first", created_at: "2026-08-14T12:00:00Z", reply_to_message_id: ""
      }],
      candidate_preflight: [{
        deployment_id: "deployment-ann", eligible: true, deterministic_score: 0,
        minimum_score: 0, signals: { profile_disabled_blocked: 0 }
      }]
    });
    expect(bodies[0]).toMatchObject({
      connection_id: "connection-1", guild_id: "guild-1", thread_id: "thread-1", burst_id: "burst-1",
      candidates: [{ deployment_id: "deployment-ann", eligible: true, deterministic_score: 0, minimum_score: 0, signals: { profile_disabled_blocked: 0 } }]
    });
    expect(result.conversation_segments[0]?.conversation_thread_id).toBe("thread-1");
    expect(result.reply_targets[0]?.context_sufficiency).toBe("sufficient");
    expect(result.speaker_plan[0]?.guidance).toBe("Answer the question.");
  });

  it("rejects a V4-shaped or non-authoritative response rather than falling back", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({
      resolver_version: "conversation-intelligence-v4-shadow-1", available: true, reason: "ok"
    })));
    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await expect(relay.resolveSmartParticipation({ message: "ordinary", deployment_ids: ["deployment-ann"] }))
      .rejects.toThrow("invalid conversation-intelligence-v3");
  });

  it.each([
    ["missing nested fields", {
      speaker_plan: [{
        deployment_id: "deployment-ann",
        turn_role: "participant",
        reason: "direct_relevance"
      }]
    }],
    ["a speaker without a reply target", { reply_targets: [] }],
    ["an unknown deployment", {
      speaker_plan: [{
        deployment_id: "deployment-unknown",
        turn_role: "participant",
        reason: "direct_relevance",
        guidance: "Answer."
      }],
      reply_targets: [{
        deployment_id: "deployment-unknown",
        segment_id: "segment-1",
        conversation_thread_id: "thread-1",
        score: 0.9,
        reason: "direct_relevance",
        grounding_level: "context_only",
        context_sufficiency: "sufficient"
      }]
    }],
    ["a non-integer count", { burst_message_count: 1.5 }],
    ["an overlong bounded field", { participation_plan_reason: "x".repeat(241) }]
  ])("rejects %s in a v3 response", async (_label, overrides) => {
    vi.stubGlobal("fetch", vi.fn(async () => v3Response(overrides)));
    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await expect(
      relay.resolveSmartParticipation({ message: "ordinary", deployment_ids: ["deployment-ann"] })
    ).rejects.toThrow("invalid conversation-intelligence-v3");
  });

  it("does not call the retired semantic-score route after resolver failure", async () => {
    const paths: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      paths.push(url.pathname);
      return jsonResponse({ detail: "Not Found" }, 404);
    }));
    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await expect(relay.resolveSmartParticipation({ message: "ordinary", deployment_ids: ["deployment-ann"] })).rejects.toThrow("HTTP 404");
    expect(paths).toEqual(["/api/smart-participation/resolve"]);
  });
});
