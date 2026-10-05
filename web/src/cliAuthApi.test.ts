import { afterEach, describe, expect, it, vi } from "vitest";

import { cliAuthApi, CliBrowserRequestError, cliErrorMessage } from "./cliAuthApi";

describe("CLI browser approval transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses cookie sessions and refuses redirects for every browser operation", async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await cliAuthApi.context();
    await cliAuthApi.grants();
    for (const [path, options] of fetcher.mock.calls) {
      expect(path).toMatch(/^\/api\/cli-auth\/(browser-context|grants)$/u);
      expect(options).toMatchObject({ credentials: "same-origin", redirect: "error", cache: "no-store" });
      expect(options.headers).not.toHaveProperty("Authorization");
    }
  });

  it("sends explicit code decisions and CSRF for all writes, with escaped grant IDs", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    await cliAuthApi.review("ABCD-EFGH", "csrf-test-value");
    await cliAuthApi.decide("ABCD-EFGH", "deny", "csrf-test-value");
    await cliAuthApi.revoke("grant/another", "csrf-test-value");
    expect(fetcher.mock.calls[0][0]).toBe("/api/cli-auth/authorizations/review");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ user_code: "ABCD-EFGH" });
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ user_code: "ABCD-EFGH", decision: "deny" });
    expect(fetcher.mock.calls[2][0]).toBe("/api/cli-auth/grants/grant%2Fanother");
    for (const [, options] of fetcher.mock.calls) {
      expect(options.headers["X-CSRF-Token"]).toBe("csrf-test-value");
      expect(options.headers).not.toHaveProperty("Authorization");
    }
  });

  it("does not expose untrusted response bodies in errors", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("sensitive-untrusted-body", { status: 403 }));
    vi.stubGlobal("fetch", fetcher);
    try {
      await cliAuthApi.context();
      throw new Error("Expected denial");
    } catch (reason) {
      expect(reason).toBeInstanceOf(CliBrowserRequestError);
      expect(String(reason)).not.toContain("sensitive-untrusted-body");
      expect(cliErrorMessage(reason, false)).toContain("Check the code");
    }
  });

  it("explains disabled, expired login and rate limits without raw error data", () => {
    expect(cliErrorMessage(new CliBrowserRequestError(404), false)).toContain("has not been enabled");
    expect(cliErrorMessage(new CliBrowserRequestError(401), false)).toContain("sign in again");
    expect(cliErrorMessage(new CliBrowserRequestError(429), false)).toContain("Too many attempts");
  });
});
