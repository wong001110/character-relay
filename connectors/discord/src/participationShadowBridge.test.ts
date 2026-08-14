import { afterEach, describe, expect, it, vi } from "vitest";

import { RelayClient } from "./relayClient.js";
import {
  buildSmartParticipationBaseEvidence,
  configureSmartParticipation,
  resetSmartParticipationState
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

function deployment(name: string): DiscordDeployment {
  return {
    deployment_id: `deployment-${name}`,
    connection_id: "connection-1",
    character_card_id: `card-${name}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    category_id: "",
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

describe("V4 deterministic shadow bridge", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetSmartParticipationState();
  });

  it("exports the same zero-semantic candidate score used by the TS scorer", () => {
    const ann = deployment("Ann");
    configureSmartParticipation({
      enabled: true,
      profiles: {
        [ann.deployment_id]: {
          style: "balanced",
          topics: ["photography"],
          keywords: ["lens"],
          cooldown_seconds: 0
        }
      }
    });

    const evidence = buildSmartParticipationBaseEvidence(
      [ann],
      "photography lens question",
      1_000
    );

    expect(evidence).toHaveLength(1);
    expect(evidence[0]?.deploymentId).toBe(ann.deployment_id);
    expect(evidence[0]?.eligible).toBe(true);
    expect(evidence[0]?.minimumScore).toBe(5);
    expect(evidence[0]?.signals.topic_match).toBe(3);
    expect(evidence[0]?.signals.keyword_match).toBe(2);
    expect(evidence[0]?.signals.semantic_match).toBe(0);
    expect(evidence[0]?.deterministicScore).toBeGreaterThanOrEqual(5);
  });

  it("forwards deterministic evidence and surfaces server shadow scores without using them for selection", async () => {
    const ann = deployment("Ann");
    const resolverBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = new URL(
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url
        );
        if (url.pathname === "/api/connectors/discord/deployments") return jsonResponse([ann]);
        if (url.pathname === "/api/smart-participation/connector-profiles") return jsonResponse({});
        if (url.pathname === "/api/smart-participation/resolve") {
          resolverBodies.push(
            JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>
          );
          return jsonResponse({
            resolver_version: "conversation-intelligence-v4-shadow-2",
            available: true,
            reason: "ok",
            model: "e5",
            dimension: 1024,
            burst_id: "",
            burst_message_count: 1,
            analysis_chars: 20,
            candidates: [
              {
                deployment_id: ann.deployment_id,
                character_card_id: ann.character_card_id,
                eligible: true,
                deterministic_score: 4.5,
                minimum_score: 5,
                deterministic_signals: { initiative: 0.5 },
                raw_e5_relevance: 0.9,
                profile_ready: true,
                semantic_points: 6,
                shadow_final_score: 10.5,
                shadow_selected: true,
                graph_evidence_count: 0,
                learned_state_evidence_count: 0,
                utility_adjustment: 0
              }
            ],
            speaker_plan: [],
            shadow_speaker_plan: [
              { deployment_id: ann.deployment_id, turn_role: "primary", reason: "deterministic_e5_shadow" }
            ],
            speaker_plan_authoritative: false,
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
    const result = await relay.scoreSmartParticipation({
      message: "ordinary unresolved message",
      deployment_ids: [ann.deployment_id],
      minimum_margin: 2,
      max_participants: 2,
      candidate_preflight: [
        {
          deployment_id: ann.deployment_id,
          eligible: true,
          deterministic_score: 4.5,
          minimum_score: 5,
          signals: { initiative: 0.5 }
        }
      ]
    });

    expect(resolverBodies[0]).toMatchObject({
      minimum_margin: 2,
      max_participants: 2,
      candidates: [
        {
          deployment_id: ann.deployment_id,
          deterministic_score: 4.5,
          minimum_score: 5,
          signals: { initiative: 0.5 }
        }
      ]
    });
    expect(result.speaker_plan_authoritative).toBe(false);
    expect(result.shadow_speaker_plan?.[0]?.deployment_id).toBe(ann.deployment_id);
    expect(result.shadow_candidate_scores?.[0]?.shadow_final_score).toBe(10.5);
    expect(result.candidates[0]?.semantic_relevance).toBe(0.9);
  });
});
