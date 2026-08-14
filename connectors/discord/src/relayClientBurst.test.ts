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

describe("RelayClient V4 burst provenance", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards scope and ordered burst messages to the V4 resolver", async () => {
    const ann = deployment("Ann");
    const resolverBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({});
        }
        if (url.pathname === "/api/smart-participation/resolve") {
          resolverBodies.push(
            JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>
          );
          return jsonResponse({
            resolver_version: "conversation-intelligence-v4-shadow-1",
            available: true,
            reason: "ok",
            model: "e5",
            dimension: 1024,
            burst_id: "burst-123",
            burst_message_count: 2,
            analysis_chars: 20,
            candidates: [],
            speaker_plan: [],
            graph_shadow_observed: true,
            graph_shadow_node_count: 3,
            graph_shadow_edge_count: 2,
            graph_used: false,
            learned_state_used: false,
            utility_used: false
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    await relay.scoreSmartParticipation({
      message: "first\nsecond",
      deployment_ids: [ann.deployment_id],
      guild_id: "guild-1",
      channel_id: "channel-1",
      thread_id: "thread-1",
      message_id: "message-2",
      author_id: "user-2",
      burst_id: "burst-123",
      burst_messages: [
        {
          message_id: "message-1",
          author_id: "user-1",
          author_display_name: "Alice",
          text: "first",
          created_at: "2026-08-14T12:00:00Z",
          reply_to_message_id: ""
        },
        {
          message_id: "message-2",
          author_id: "user-2",
          author_display_name: "Bob",
          text: "second",
          created_at: "2026-08-14T12:00:01Z",
          reply_to_message_id: ""
        }
      ]
    });

    expect(resolverBodies[0]).toMatchObject({
      connection_id: "connection-1",
      guild_id: "guild-1",
      channel_id: "channel-1",
      thread_id: "thread-1",
      message_id: "message-2",
      author_id: "user-2",
      burst_id: "burst-123"
    });
    expect(resolverBodies[0]?.burst_messages).toEqual([
      {
        message_id: "message-1",
        author_id: "user-1",
        author_display_name: "Alice",
        text: "first",
        created_at: "2026-08-14T12:00:00Z",
        reply_to_message_id: ""
      },
      {
        message_id: "message-2",
        author_id: "user-2",
        author_display_name: "Bob",
        text: "second",
        created_at: "2026-08-14T12:00:01Z",
        reply_to_message_id: ""
      }
    ]);
  });

  it("keeps the legacy fallback payload narrow", async () => {
    const ann = deployment("Ann");
    let legacyBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") return jsonResponse([ann]);
        if (url.pathname === "/api/smart-participation/connector-profiles") return jsonResponse({});
        if (url.pathname === "/api/smart-participation/resolve") {
          return jsonResponse({ detail: "Not Found" }, 404);
        }
        if (url.pathname === "/api/smart-participation/semantic-score") {
          legacyBody = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
          return jsonResponse({
            available: false,
            reason: "legacy",
            model: "",
            dimension: 0,
            candidates: []
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    await relay.scoreSmartParticipation({
      message: "ordinary",
      deployment_ids: [ann.deployment_id],
      guild_id: "guild-1",
      channel_id: "channel-1",
      burst_id: "burst-123"
    });

    expect(legacyBody).toEqual({
      connection_id: "connection-1",
      message: "ordinary",
      deployment_ids: [ann.deployment_id]
    });
  });
});
