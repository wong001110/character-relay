import { afterEach, describe, expect, it, vi } from "vitest";

import {
  correctBelief,
  listKnowledgeGapCandidates,
  loadConversationStructurePage,
  reviewKnowledgeGapCandidate
} from "./conversationStructureApi";

afterEach(() => vi.unstubAllGlobals());

describe("conversation structure pagination adapter", () => {
  it("keeps candidate review and belief correction inside the selected deployment", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ gap: {}, candidate: {} }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ action: "correct", belief: {}, previous_belief_ids: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await listKnowledgeGapCandidates("deployment/a", "gap/a");
    await reviewKnowledgeGapCandidate("deployment/a", "gap/a", "candidate/a", {
      action: "accept",
      validated_evidence_ref: "discovery_item:discovery/a",
      resolved_fields: ["birthplace"],
      confidence: 0.8
    });
    await correctBelief("deployment/a", "belief/a", {
      value_text: "corrected",
      domain: "canonical",
      reason: "verified source",
      confidence: 0.9
    });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/deployments/deployment%2Fa/knowledge-gaps/gap%2Fa/candidates?include_terminal=false",
      "/api/deployments/deployment%2Fa/knowledge-gaps/gap%2Fa/candidates/candidate%2Fa/review",
      "/api/deployments/deployment%2Fa/beliefs/belief%2Fa/correct"
    ]);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ action: "accept", validated_evidence_ref: "discovery_item:discovery/a", resolved_fields: ["birthplace"], confidence: 0.8 })
    });
  });

  it("keeps legacy bounded arrays usable as an unpaged fixture", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ deployment_id: "dep-1", threads: [{ id: "thread-1" }] }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const page = await loadConversationStructurePage("dep/1");

    expect(page.threads).toEqual([{ id: "thread-1" }]);
    expect(page.pages.threads).toMatchObject({ items: [{ id: "thread-1" }], paged: false, has_more: false });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/deployments/dep%2F1/conversation-structure");
  });

  it("reads nested collection metadata and sends that collection cursor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          deployment_id: "dep-1",
          relations: [{ id: "relation-2" }],
          pagination: { relations: { next_cursor: "cursor/2", has_more: true } }
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const page = await loadConversationStructurePage("dep-1", {
      collection: "relations",
      cursor: "cursor/1",
      limit: 12
    });

    expect(page.pages.relations).toMatchObject({
      items: [{ id: "relation-2" }],
      next_cursor: "cursor/2",
      has_more: true,
      paged: true
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/deployments/dep-1/conversation-structure?limit=12&relations_cursor=cursor%2F1"
    );
  });
});
