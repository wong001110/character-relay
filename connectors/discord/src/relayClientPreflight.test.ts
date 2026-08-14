import { afterEach, describe, expect, it, vi } from "vitest";

import { RelayClient } from "./relayClient.js";
import type { DiscordDeployment } from "./types.js";

function deployment(name: string): DiscordDeployment {
  return {
    deployment_id: `deployment-${name}`,
    connection_id: "connection-1",
    character_card_id: `character-${name}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    category_id: "category-1",
    server_profile_id: "",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: "smart",
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: "",
    address_aliases: [name],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    orchestration_mode: "off"
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function v4Response(ann: DiscordDeployment): Response {
  return jsonResponse({
    resolver_version: "conversation-intelligence-v4-shadow-1",
    available: true,
    reason: "ok",
    model: "e5",
    dimension: 1024,
    burst_id: "",
    burst_message_count: 1,
    analysis_chars: 25,
    candidates: [
      {
        deployment_id: ann.deployment_id,
        character_card_id: ann.character_card_id,
        eligible: true,
        deterministic_score: 0,
        minimum_score: 0,
        raw_e5_relevance: 0.81,
        profile_ready: true,
        graph_evidence_count: 0,
        learned_state_evidence_count: 0,
        utility_adjustment: 0
      }
    ],
    speaker_plan: [],
    graph_used: false,
    learned_state_used: false,
    utility_used: false
  });
}

describe("RelayClient Smart Participation preflight", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.DISCORD_GROUP_ADDRESS_ALIASES;
  });

  it("uses cached deployment metadata to skip all semantic routes for a named Character", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    const paths: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url
      );
      paths.push(url.pathname);
      if (url.pathname === "/api/connectors/discord/deployments") {
        return jsonResponse([ann, ning]);
      }
      if (url.pathname === "/api/smart-participation/connector-profiles") {
        return jsonResponse({});
      }
      throw new Error(`unexpected request ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    const result = await relay.scoreSmartParticipation({
      message: "Ann, what do you think?",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(result.available).toBe(false);
    expect(result.reason).toBe("explicit_audience_preflight:selected_alias");
    expect(paths).not.toContain("/api/smart-participation/resolve");
    expect(paths).not.toContain("/api/smart-participation/semantic-score");
  });

  it("also skips semantic scoring for configured group addressing", async () => {
    process.env.DISCORD_GROUP_ADDRESS_ALIASES = "team";
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    const semanticPaths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({});
        }
        semanticPaths.push(url.pathname);
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    const result = await relay.scoreSmartParticipation({
      message: "team, what do you think?",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(result.reason).toBe("explicit_audience_preflight:selected_all");
    expect(semanticPaths).toEqual([]);
  });

  it("uses the V4 resolver for ordinary unresolved group chat", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let resolverCalls = 0;
    let legacyCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({});
        }
        if (url.pathname === "/api/smart-participation/resolve") {
          resolverCalls += 1;
          return v4Response(ann);
        }
        if (url.pathname === "/api/smart-participation/semantic-score") {
          legacyCalls += 1;
          throw new Error("legacy semantic route should not run when V4 is available");
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    const result = await relay.scoreSmartParticipation({
      message: "the weather changed again",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(result.available).toBe(true);
    expect(result.reason).toBe("v4_resolver:ok");
    expect(resolverCalls).toBe(1);
    expect(legacyCalls).toBe(0);
    expect(result.candidates[0]?.deployment_id).toBe(ann.deployment_id);
    expect(result.candidates[0]?.semantic_relevance).toBe(0.81);
  });

  it("falls back to the legacy semantic route only when the V4 endpoint is absent", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let resolverCalls = 0;
    let legacyCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({});
        }
        if (url.pathname === "/api/smart-participation/resolve") {
          resolverCalls += 1;
          return jsonResponse({ detail: "Not Found" }, 404);
        }
        if (url.pathname === "/api/smart-participation/semantic-score") {
          legacyCalls += 1;
          return jsonResponse({
            available: true,
            reason: "legacy_ok",
            model: "e5",
            dimension: 1024,
            candidates: [
              {
                deployment_id: ann.deployment_id,
                character_card_id: ann.character_card_id,
                semantic_relevance: 0.79,
                profile_ready: true
              }
            ]
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    const result = await relay.scoreSmartParticipation({
      message: "ordinary unresolved message",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(resolverCalls).toBe(1);
    expect(legacyCalls).toBe(1);
    expect(result.reason).toBe("legacy_ok");
  });

  it("does not hide a V4 server failure by silently falling back to legacy behavior", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let legacyCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({});
        }
        if (url.pathname === "/api/smart-participation/resolve") {
          return jsonResponse({ detail: "resolver failed" }, 500);
        }
        if (url.pathname === "/api/smart-participation/semantic-score") {
          legacyCalls += 1;
          return jsonResponse({});
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();

    await expect(
      relay.scoreSmartParticipation({
        message: "ordinary unresolved message",
        deployment_ids: [ann.deployment_id, ning.deployment_id]
      })
    ).rejects.toThrow("HTTP 500");
    expect(legacyCalls).toBe(0);
  });
});
