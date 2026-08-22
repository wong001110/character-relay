import { beforeEach, describe, expect, it } from "vitest";

import {
  configureSmartParticipation,
  consumeSmartSelection,
  markExplicitSmartSelections,
  markV3SmartParticipationSelections,
  preflightSmartParticipationRuntime,
  resetSmartParticipationState
} from "./smartParticipation.js";
import { resolveAudience } from "./routing.js";
import type { DiscordDeployment } from "./types.js";

const ann: DiscordDeployment = {
  deployment_id: "deployment-ann", connection_id: "connection-1", character_card_id: "card-ann",
  character_display_name: "Ann", workspace_id: "guild-1", workspace_name: "Guild",
  channel_id: "channel-1", channel_name: "general", thread_id: "", thread_name: "", category_id: "",
  server_profile_id: "", channel_scope_mode: "exact", excluded_channel_ids: [], excluded_category_ids: [],
  participation_mode: "smart", version_label: "Current", status: "active", identity_mode: "webhook",
  identity_display_name: "Ann", identity_avatar_url: "", address_aliases: ["Ann"], webhook_status: "pending",
  webhook_id: null, webhook_token: null, orchestration_mode: "off"
};

const ning: DiscordDeployment = {
  ...ann,
  deployment_id: "deployment-ning",
  character_card_id: "card-ning",
  character_display_name: "Ning",
  identity_display_name: "Ning",
  address_aliases: ["Ning"]
};

describe("Smart Participation v3 hard gates", () => {
  beforeEach(() => {
    resetSmartParticipationState();
    configureSmartParticipation({ enabled: true, channelCooldownSeconds: 45, windowSeconds: 600, maxRepliesPerWindow: 1 });
  });

  it("leaves ordinary selection to the v3 resolver", () => {
    expect(resolveAudience([ann], "ordinary unresolved message").deployments).toEqual([]);
    expect(preflightSmartParticipationRuntime([ann], "ordinary unresolved message", 1_000)).toEqual({
      skipResolver: false, reason: "resolver_required", eligibleDeploymentIds: [ann.deployment_id]
    });
  });

  it("does not apply a v3 cooldown until the selected Character is admitted", () => {
    markV3SmartParticipationSelections([ann], 1_000, "scope");
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
    expect(preflightSmartParticipationRuntime([ann], "next message", 2_000, "scope").reason).toBe("channel_cooldown");
  });

  it("keeps explicit address eligible without turning it into proactive authority", () => {
    markExplicitSmartSelections([ann], 1_000, "scope");
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
    expect(preflightSmartParticipationRuntime([ann], "next message", 2_000, "scope").reason).toBe("resolver_required");
  });

  it("keeps channel admission state isolated by runtime scope", () => {
    markV3SmartParticipationSelections([ann], 1_000, "scope-a");
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    expect(preflightSmartParticipationRuntime([ann], "next message", 2_000, "scope-a").reason).toBe("channel_cooldown");
    expect(preflightSmartParticipationRuntime([ann], "next message", 2_000, "scope-b")).toEqual({
      skipResolver: false,
      reason: "resolver_required",
      eligibleDeploymentIds: [ann.deployment_id]
    });
  });

  it("applies per-character profile blocks before calling v3", () => {
    configureSmartParticipation({
      profiles: {
        [ann.deployment_id]: { enabled: false },
        [ning.deployment_id]: { avoid_phrases: ["private topic"] }
      }
    });

    expect(preflightSmartParticipationRuntime([ann, ning], "a private topic", 1_000)).toEqual({
      skipResolver: true,
      reason: "all_candidates_blocked",
      eligibleDeploymentIds: []
    });
  });

  it("enforces the proactive reply window only after admitted v3 turns", () => {
    configureSmartParticipation({ channelCooldownSeconds: 0, maxRepliesPerWindow: 1 });
    markV3SmartParticipationSelections([ann], 1_000, "scope");
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    expect(preflightSmartParticipationRuntime([ann, ning], "next message", 2_000, "scope")).toEqual({
      skipResolver: true,
      reason: "channel_rate_limit",
      eligibleDeploymentIds: []
    });
  });
});
