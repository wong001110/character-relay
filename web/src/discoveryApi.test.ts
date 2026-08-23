import { afterEach, describe, expect, it, vi } from "vitest";

import { discoveryApi } from "./discoveryApi";

afterEach(() => vi.unstubAllGlobals());

describe("discovery pagination adapter", () => {
  it("normalizes the legacy items-only response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [{ id: "session-1" }] }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const page = await discoveryApi.sessions("dep/1");

    expect(page).toEqual({ items: [{ id: "session-1" }], next_cursor: null, has_more: false, paged: false });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/deployments/dep%2F1/discovery/sessions?limit=20");
  });

  it("passes the opaque continuation cursor through to the server", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], next_cursor: "next/2", has_more: true }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await discoveryApi.shares("dep-1", { cursor: "next/1", limit: 12 });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/deployments/dep-1/discovery/shares?limit=12&cursor=next%2F1");
  });
});
