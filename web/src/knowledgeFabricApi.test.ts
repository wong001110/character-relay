import { afterEach, describe, expect, it, vi } from "vitest";

import { knowledgeFabricApi } from "./knowledgeFabricApi";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Knowledge Fabric Portal API", () => {
  it("keeps the selected server identity opaque and URL-encoded", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response([
          {
            id: "scope/one",
            platform: "discord",
            connection_id: "connection-a",
            workspace_id: "guild-a",
            created_at: "2026-08-26T00:00:00Z",
            updated_at: "2026-08-26T00:00:00Z"
          }
        ])
      )
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.listScopes();
    await knowledgeFabricApi.listCorpora("scope/one");
    await knowledgeFabricApi.listGlobalAccess("scope/one");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge-fabric/server-scopes",
      expect.objectContaining({
        credentials: "include",
        headers: { "Content-Type": "application/json" }
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/knowledge-fabric/server-scopes/scope%2Fone/global-corpora/access",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge-fabric/server-scopes/scope%2Fone/corpora",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("sends source and policy writes only to the selected server scope", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          id: "source-a",
          corpus_id: "corpus/a",
          source_type: "website",
          locator: "https://example.test/reference",
          authority_profile: "standard",
          enabled: true,
          status: "registered"
        })
      )
      .mockResolvedValueOnce(
        response({
          deployment_id: "deployment/a",
          character_card_id: "card-a",
          corpus_id: "corpus/a",
          effect: "allow"
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.createLocalSource("scope/a", "corpus/a", {
      source_type: "website",
      locator: "https://example.test/reference",
      authority_profile: "standard"
    });
    await knowledgeFabricApi.setCharacterPolicy(
      "scope/a",
      "deployment/a",
      "corpus/a",
      "allow"
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge-fabric/server-scopes/scope%2Fa/corpora/corpus%2Fa/sources",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({
          source_type: "website",
          locator: "https://example.test/reference",
          authority_profile: "standard",
          parser_profile: {},
          sync_policy: {},
          freshness_policy: {}
        })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge-fabric/server-scopes/scope%2Fa/deployments/deployment%2Fa/corpora/corpus%2Fa/epistemic-policy",
      expect.objectContaining({
        method: "PUT",
        credentials: "include",
        body: JSON.stringify({ effect: "allow" })
      })
    );
  });

  it("uses the scoped local Corpus and policy read endpoints", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          id: "corpus-a",
          name: "Server notes",
          description: "",
          owner_type: "server",
          owner_id: "scope-a",
          visibility: "private",
          default_authority_profile: "standard",
          status: "active",
          overlay_mode: null,
          created_at: "2026-08-26T00:00:00Z",
          updated_at: "2026-08-26T00:00:00Z"
        })
      )
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.createLocalCorpus("scope/a", {
      name: "Server notes",
      description: "",
      default_authority_profile: "standard"
    });
    await knowledgeFabricApi.listLocalSources("scope/a", "corpus/a");
    await knowledgeFabricApi.listCharacterPolicies("scope/a");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge-fabric/server-scopes/scope%2Fa/corpora",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "Server notes",
          description: "",
          default_authority_profile: "standard"
        })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge-fabric/server-scopes/scope%2Fa/corpora/corpus%2Fa/sources",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/knowledge-fabric/server-scopes/scope%2Fa/character-corpus-policies",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("lists global Corpus availability inside the selected scope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.listAvailableGlobal("scope/a");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge-fabric/server-scopes/scope%2Fa/available-global-corpora",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("uses the Super Admin Global Library, redacted health, and durable schedule endpoints", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({}))
      .mockResolvedValueOnce(response({}))
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({}))
      .mockResolvedValueOnce(response({ pending: 1, running: 0, failed: 2 }));
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.listGlobalCorpora();
    await knowledgeFabricApi.createGlobalCorpus({
      name: "World notes",
      description: "Approved world evidence",
      default_authority_profile: "standard"
    });
    await knowledgeFabricApi.createGlobalSource("corpus/a", {
      source_type: "website",
      locator: "https://example.test/reference",
      authority_profile: "standard"
    });
    await knowledgeFabricApi.listGlobalOperationalSources("corpus/a");
    await knowledgeFabricApi.configureExternalSourceSchedule("source/a", {
      enabled: true,
      interval_seconds: 900
    });
    await knowledgeFabricApi.retryFailedDerivedWork("source/a");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge-fabric/admin/corpora",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge-fabric/admin/corpora",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "World notes",
          description: "Approved world evidence",
          default_authority_profile: "standard"
        })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/knowledge-fabric/admin/corpora/corpus%2Fa/sources",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source_type: "website",
          locator: "https://example.test/reference",
          authority_profile: "standard",
          parser_profile: {},
          sync_policy: {},
          freshness_policy: {}
        })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/knowledge-fabric/admin/corpora/corpus%2Fa/operational-sources",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/knowledge-fabric/admin/sources/source%2Fa/external-sync-schedule",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ enabled: true, interval_seconds: 900 })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/api/knowledge-fabric/admin/sources/source%2Fa/derived-work/retry",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("keeps Query Inspector scoped to the authorized server route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ hits: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.inspectQuery("scope/a", {
      query: "What changed?",
      mode: "overview"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge-fabric/server-scopes/scope%2Fa/query-inspector",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ query: "What changed?", mode: "overview" })
      })
    );
  });

  it("keeps grant and overlay writes distinct", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          corpus_id: "corpus-a",
          grantee_type: "server_scope",
          grantee_id: "scope-a",
          enabled: true,
          access_mode: "read",
          updated_at: "2026-08-26T00:00:00Z"
        })
      )
      .mockResolvedValueOnce(
        response({ corpus_id: "corpus-a", mode: "deny", updated_at: "2026-08-26T00:00:00Z" })
      );
    vi.stubGlobal("fetch", fetchMock);

    await knowledgeFabricApi.grantGlobal("scope-a", "corpus-a", true);
    await knowledgeFabricApi.setOverlay("scope-a", "corpus-a", "deny");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/knowledge-fabric/server-scopes/scope-a/global-corpora/corpus-a/grant",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/knowledge-fabric/server-scopes/scope-a/global-corpora/corpus-a/overlay",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ mode: "deny" }) })
    );
  });

  it("surfaces the API detail instead of accepting a failed management action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "Not authorized." }, 404)));

    await expect(knowledgeFabricApi.listAvailableGlobal("unknown")).rejects.toMatchObject({
      message: "Not authorized."
    });
  });

  it("preserves a JSON error body whose detail is not a user-facing string", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: { code: "denied" } }, 403)));

    await expect(knowledgeFabricApi.listAvailableGlobal("unknown")).rejects.toThrow(
      '{"detail":{"code":"denied"}}'
    );
  });

  it("preserves non-JSON errors and a status-only failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("Gateway unavailable", { status: 502 }))
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(knowledgeFabricApi.listScopes()).rejects.toThrow("Gateway unavailable");
    await expect(knowledgeFabricApi.listScopes()).rejects.toThrow("Request failed with 503");
  });
});
