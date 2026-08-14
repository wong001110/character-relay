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

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

describe("RelayClient Smart Participation preflight", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.DISCORD_GROUP_ADDRESS_ALIASES;
  });

  it("uses cached deployment metadata to skip the semantic endpoint for a named Character", async () => {
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
      if (url.pathname === "/api/smart-participation/semantic-score") {
        throw new Error("semantic endpoint must not be called for explicit audience");
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
    expect(paths).not.toContain("/api/smart-participation/semantic-score");
  });

  it("also skips semantic scoring for configured group addressing", async () => {
    process.env.DISCORD_GROUP_ADDRESS_ALIASES = "team";
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let semanticCalls = 0;
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
        if (url.pathname === "/api/smart-participation/semantic-score") {
          semanticCalls += 1;
          return jsonResponse({
            available: true,
            reason: "ok",
            model: "e5",
            dimension: 1024,
            candidates: []
          });
        }
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
    expect(semanticCalls).toBe(0);
  });

  it("still calls the semantic endpoint for ordinary unresolved group chat", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let semanticCalls = 0;
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
        if (url.pathname === "/api/smart-participation/semantic-score") {
          semanticCalls += 1;
          return jsonResponse({
            available: true,
            reason: "ok",
            model: "e5",
            dimension: 1024,
            candidates: [
              {
                deployment_id: ann.deployment_id,
                character_card_id: ann.character_card_id,
                semantic_relevance: 0.81,
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
      message: "the weather changed again",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(result.available).toBe(true);
    expect(semanticCalls).toBe(1);
    expect(result.candidates[0]?.deployment_id).toBe(ann.deployment_id);
  });
});
