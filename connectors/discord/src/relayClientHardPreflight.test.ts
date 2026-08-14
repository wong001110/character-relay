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

describe("RelayClient hard Smart Participation preflight", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not call the V4 resolver when every smart candidate is disabled", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    const paths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        paths.push(url.pathname);
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({
            [ann.deployment_id]: {
              enabled: false,
              style: "balanced",
              group_role: "independent",
              topics: [],
              keywords: [],
              trigger_phrases: [],
              avoid_phrases: [],
              initiative: 0.45,
              minimum_score: 5,
              cooldown_seconds: 120,
              preferred_follow_up_character_card_id: "",
              follow_up_window_seconds: 30
            },
            [ning.deployment_id]: {
              enabled: false,
              style: "balanced",
              group_role: "independent",
              topics: [],
              keywords: [],
              trigger_phrases: [],
              avoid_phrases: [],
              initiative: 0.45,
              minimum_score: 5,
              cooldown_seconds: 120,
              preferred_follow_up_character_card_id: "",
              follow_up_window_seconds: 30
            }
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      })
    );

    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");
    await relay.listDeployments();
    const result = await relay.scoreSmartParticipation({
      message: "ordinary unresolved group message",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    expect(result.available).toBe(false);
    expect(result.reason).toBe("hard_preflight_no_eligible_candidates");
    expect(paths).not.toContain("/api/smart-participation/resolve");
    expect(paths).not.toContain("/api/smart-participation/semantic-score");
  });

  it("sends mixed eligibility so blocked candidates are not embedded by the backend", async () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    let resolverBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") {
          return jsonResponse([ann, ning]);
        }
        if (url.pathname === "/api/smart-participation/connector-profiles") {
          return jsonResponse({
            [ning.deployment_id]: {
              enabled: true,
              style: "balanced",
              group_role: "independent",
              topics: [],
              keywords: [],
              trigger_phrases: [],
              avoid_phrases: ["private topic"],
              initiative: 0.45,
              minimum_score: 6,
              cooldown_seconds: 120,
              preferred_follow_up_character_card_id: "",
              follow_up_window_seconds: 30
            }
          });
        }
        if (url.pathname === "/api/smart-participation/resolve") {
          resolverBody = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
          return jsonResponse({
            resolver_version: "conversation-intelligence-v4-shadow-1",
            available: true,
            reason: "ok",
            model: "e5",
            dimension: 1024,
            burst_id: "",
            burst_message_count: 1,
            analysis_chars: 20,
            candidates: [],
            speaker_plan: [],
            graph_shadow_observed: false,
            graph_shadow_node_count: 0,
            graph_shadow_edge_count: 0,
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
      message: "this is a private topic today",
      deployment_ids: [ann.deployment_id, ning.deployment_id]
    });

    const candidates = (resolverBody?.candidates ?? []) as Array<Record<string, unknown>>;
    expect(candidates).toEqual([
      {
        deployment_id: ann.deployment_id,
        eligible: true,
        deterministic_score: 0,
        minimum_score: 5,
        signals: {}
      },
      {
        deployment_id: ning.deployment_id,
        eligible: false,
        deterministic_score: 0,
        minimum_score: 6,
        signals: { avoid_phrase_blocked: 1 }
      }
    ]);
  });
});
