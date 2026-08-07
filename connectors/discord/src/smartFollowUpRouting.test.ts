import { beforeEach, describe, expect, it } from "vitest";

import { resolveBotTagAudience } from "./routing.js";
import {
  configureSmartParticipation,
  resetSmartParticipationState,
  type DiscordPortalParticipationProfile
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

function deployment(
  id: string,
  characterCardId: string,
  name: string,
  profile: Partial<DiscordPortalParticipationProfile>
): DiscordDeployment {
  return {
    deployment_id: id,
    connection_id: "connection-1",
    character_card_id: characterCardId,
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
    smart_participation_profile: {
      character_card_id: characterCardId,
      configured: true,
      enabled: true,
      style: "balanced",
      group_role: "independent",
      topics: [],
      keywords: [],
      trigger_phrases: [],
      avoid_phrases: [],
      cooldown_seconds: 120,
      preferred_follow_up_character_card_id: "",
      follow_up_window_seconds: 30,
      ...profile
    }
  } as DiscordDeployment;
}

describe("Smart Primary to Secondary routing", () => {
  beforeEach(() => {
    resetSmartParticipationState();
    configureSmartParticipation({
      enabled: true,
      channelCooldownSeconds: 0,
      windowSeconds: 600,
      maxRepliesPerWindow: 10,
      automaticFollowUpsEnabled: true
    });
  });

  it("keeps automatic Primary-to-Secondary follow-up disabled unless explicitly enabled", () => {
    configureSmartParticipation({
      enabled: true,
      automaticFollowUpsEnabled: false
    });
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const audience = resolveBotTagAudience(
      [serena, mia],
      "That conclusion is doing a lot of work.",
      serena.deployment_id
    );

    expect(audience.reason).toBe("not_found");
    expect(audience.deployments).toEqual([]);
  });

  it("routes an untagged Primary reply to its configured Secondary when legacy follow-up is enabled", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const audience = resolveBotTagAudience(
      [serena, mia],
      "That conclusion is doing a lot of work.",
      serena.deployment_id
    );

    expect(audience.reason).toBe("selected_smart_follow_up");
    expect(audience.deployments.map((item) => item.deployment_id)).toEqual(["mia"]);
    expect(audience.text).toBe("That conclusion is doing a lot of work.");
  });

  it("keeps an explicit character Tag ahead of automatic follow-up", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const audience = resolveBotTagAudience(
      [serena, mia],
      "@Mia, take this one.",
      serena.deployment_id
    );

    expect(audience.reason).toBe("selected_alias");
    expect(audience.deployments.map((item) => item.deployment_id)).toEqual(["mia"]);
    expect(audience.text).toBe("take this one.");
  });

  it("does not auto-follow after a Secondary turn", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const audience = resolveBotTagAudience(
      [serena, mia],
      "One last punchline.",
      mia.deployment_id
    );

    expect(audience.reason).toBe("not_found");
    expect(audience.deployments).toEqual([]);
  });
});
