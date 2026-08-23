import { afterEach, describe, expect, it, vi } from "vitest";

import { loadConversationStructurePage } from "./conversationStructureApi";

afterEach(() => vi.unstubAllGlobals());

describe("conversation structure pagination adapter", () => {
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
