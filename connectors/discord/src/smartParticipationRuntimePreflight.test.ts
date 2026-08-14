import { afterEach, describe, expect, it } from "vitest";

import {
  configureSmartParticipation,
  consumeSmartSelection,
  evaluateSmartParticipation,
  preflightSmartParticipationRuntime,
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
    channel_id: "server-wide-template",
    channel_name: "all except",
    thread_id: "",
    thread_name: "",
    category_id: "",
    server_profile_id: "profile-1",
    channel_scope_mode: "all_except",
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

function scope(channel: string): string {
  return ["connection-1", "guild-1", channel, ""].join(":");
}

describe("Smart Participation runtime preflight", () => {
  afterEach(() => {
    resetSmartParticipationState();
  });

  it("skips E5 for low-information turns that the existing runtime resolves without semantics", () => {
    const ann = deployment("Ann");
    configureSmartParticipation({ enabled: true });

    expect(preflightSmartParticipationRuntime([ann], "嗯", 1_000, scope("general"))).toEqual({
      skipSemantic: true,
      reason: "low_information_message",
      semanticCandidateDeploymentIds: []
    });
  });

  it("uses the actual runtime channel scope for server-wide cooldown state", () => {
    const ann = deployment("Ann");
    configureSmartParticipation({
      enabled: true,
      channelCooldownSeconds: 45,
      maxRepliesPerWindow: 3,
      profiles: {
        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 0 }
      }
    });

    const selected = evaluateSmartParticipation(
      [ann],
      "photography workflow",
      1_000,
      { [ann.deployment_id]: 0.9 },
      scope("channel-a")
    );
    expect(selected.selectedDeployment?.deployment_id).toBe(ann.deployment_id);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    expect(
      preflightSmartParticipationRuntime([ann], "another topic", 2_000, scope("channel-a")).reason
    ).toBe("channel_cooldown");
    expect(
      preflightSmartParticipationRuntime([ann], "another topic", 2_000, scope("channel-b"))
    ).toEqual({
      skipSemantic: false,
      reason: "semantic_required",
      semanticCandidateDeploymentIds: [ann.deployment_id]
    });
  });

  it("skips E5 when the current channel has reached the proactive reply window limit", () => {
    const ann = deployment("Ann");
    configureSmartParticipation({
      enabled: true,
      channelCooldownSeconds: 0,
      windowSeconds: 600,
      maxRepliesPerWindow: 1,
      profiles: {
        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 0 }
      }
    });

    evaluateSmartParticipation(
      [ann],
      "photography workflow",
      1_000,
      { [ann.deployment_id]: 0.9 },
      scope("channel-a")
    );
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    expect(
      preflightSmartParticipationRuntime([ann], "new question", 2_000, scope("channel-a")).reason
    ).toBe("channel_rate_limit");
  });

  it("removes only cooldown-blocked characters from semantic candidates", () => {
    const ann = deployment("Ann");
    const ning = deployment("Ning");
    configureSmartParticipation({
      enabled: true,
      channelCooldownSeconds: 0,
      maxRepliesPerWindow: 3,
      profiles: {
        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 120 },
        [ning.deployment_id]: { style: "balanced", cooldown_seconds: 0 }
      }
    });

    evaluateSmartParticipation(
      [ann],
      "photography workflow",
      1_000,
      { [ann.deployment_id]: 0.9 },
      scope("channel-a")
    );
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    expect(
      preflightSmartParticipationRuntime(
        [ann, ning],
        "another unrelated discussion",
        2_000,
        scope("channel-b")
      )
    ).toEqual({
      skipSemantic: false,
      reason: "semantic_required",
      semanticCandidateDeploymentIds: [ning.deployment_id]
    });
  });
});
