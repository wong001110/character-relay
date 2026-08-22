import { afterEach, describe, expect, it, vi } from "vitest";

import { discordDebugCaptureApi } from "./discordDebugCaptureApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Discord debug capture API", () => {
  it("treats a forbidden access probe as unavailable", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(discordDebugCaptureApi.access()).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/discord-debug-captures/access",
      expect.objectContaining({ cache: "no-store", credentials: "include" })
    );
  });

  it("starts a bounded capture using the authenticated browser session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "session-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await discordDebugCaptureApi.startSession("profile/one", 60);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/admin/discord-debug-captures/sessions");
    expect(init).toMatchObject({
      method: "POST",
      cache: "no-store",
      credentials: "include"
    });
    expect(JSON.parse(String(init.body))).toEqual({
      server_profile_id: "profile/one",
      ttl_minutes: 60
    });
  });

  it("encodes record and session identifiers in read and clear requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ items: [], page: 1, page_size: 100, total: 0, pages: 1 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "record/one", payload: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ deleted_count: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    await discordDebugCaptureApi.listRecords("session/one");
    await discordDebugCaptureApi.recordDetail("record/one");
    await discordDebugCaptureApi.clearRecords("session/one");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/admin/discord-debug-captures/sessions/session%2Fone/records/page?page=1&page_size=100"
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "/api/admin/discord-debug-captures/records/record%2Fone"
    );
    expect(fetchMock.mock.calls[2]).toEqual([
      "/api/admin/discord-debug-captures/sessions/session%2Fone/records",
      expect.objectContaining({ method: "DELETE", cache: "no-store" })
    ]);
  });
});
