import { describe, expect, it } from "vitest";

import type { DiscordPortalParticipationProfile } from "./smartParticipation.js";
import { preflightSmartParticipationCandidate } from "./smartParticipationPreflight.js";
import type { DiscordDeployment } from "./types.js";

type DeploymentWithProfile = DiscordDeployment & {
  smart_participation_profile?: DiscordPortalParticipationProfile | null;
};

function deployment(): DeploymentWithProfile {
  return {
    deployment_id: "deployment-ann",
    connection_id: "connection-1",
    character_card_id: "card-ann",
    character_display_name: "Ann",
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
    identity_display_name: "Ann",
    identity_avatar_url: "",
    address_aliases: ["Ann"],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    orchestration_mode: "off"
  };
}

describe("Smart Participation hard preflight", () => {
  it("blocks a disabled persisted profile before E5", () => {
    const value = deployment();
    value.smart_participation_profile = {
      character_card_id: value.character_card_id,
      configured: true,
      enabled: false,
      style: "balanced",
      group_role: "independent",
      topics: [],
      keywords: [],
      trigger_phrases: [],
      avoid_phrases: [],
      cooldown_seconds: 120,
      preferred_follow_up_character_card_id: "",
      follow_up_window_seconds: 30
    };

    const result = preflightSmartParticipationCandidate(value, "ordinary message");

    expect(result.eligible).toBe(false);
    expect(result.reason).toBe("profile_disabled");
    expect(result.minimumScore).toBe(0);
    expect(result.signals).toEqual({ profile_disabled_blocked: 1 });
  });

  it("reuses normalized avoid phrases as an authoritative hard block", () => {
    const value = deployment();
    value.smart_participation_profile = {
      character_card_id: value.character_card_id,
      configured: true,
      enabled: true,
      style: "balanced",
      group_role: "independent",
      topics: ["photography"],
      keywords: [],
      trigger_phrases: [],
      avoid_phrases: ["do not join this"],
      cooldown_seconds: 120,
      preferred_follow_up_character_card_id: "",
      follow_up_window_seconds: 30
    };

    const result = preflightSmartParticipationCandidate(
      value,
      "  DO   NOT JOIN THIS conversation  "
    );

    expect(result.eligible).toBe(false);
    expect(result.reason).toBe("avoid_phrase");
    expect(result.minimumScore).toBe(0);
    expect(result.signals).toEqual({ avoid_phrase_blocked: 1 });
  });

  it("keeps an ordinary smart candidate eligible without inventing a score", () => {
    const result = preflightSmartParticipationCandidate(
      deployment(),
      "ordinary unresolved group chat"
    );

    expect(result.eligible).toBe(true);
    expect(result.reason).toBe("eligible");
    expect(result.signals).toEqual({});
  });
});
