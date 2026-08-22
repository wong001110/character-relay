import { afterEach, describe, expect, it, vi } from "vitest";

import { api, pollIntervalForMode } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("live polling cadence", () => {
  it("uses a low-frequency Watch cadence", () => {
    expect(pollIntervalForMode("watch")).toBe(1200);
  });

  it("keeps Fast responsive without 180ms request spam", () => {
    expect(pollIntervalForMode("fast")).toBe(450);
  });
});

describe("account administration requests", () => {
  it("requests a bounded session page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], page: 2, page_size: 20, total: 21, pages: 2 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.listSessionsPage(2, 20);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/sessions?page=2&page_size=20",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("encodes a bounded account search", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], page: 1, page_size: 20, total: 0, pages: 1 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.listAdminUsersPage({ search: "ann+ops@example.com", pageSize: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/users?page=1&page_size=20&search=ann%2Bops%40example.com",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("deletes the selected administration account", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ affected: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.deleteAdminUser("account/1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/users/account%2F1",
      expect.objectContaining({ method: "DELETE", credentials: "include" })
    );
  });
});
