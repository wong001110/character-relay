import { beforeEach, describe, expect, it } from "vitest";

import {
  configureSmartParticipation,
  evaluateSmartFollowUp,
  evaluateSmartParticipation,
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
  const portalProfile: DiscordPortalParticipationProfile = {
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
  };
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
    address_aliases: [],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    smart_participation_profile: portalProfile
  } as DiscordDeployment;
}

describe("Portal Smart Participation profiles", () => {
  beforeEach(() => {
    resetSmartParticipationState();
    configureSmartParticipation({
      enabled: true,
      profiles: {
        default: {
          keywords: ["legacy-env-keyword"],
          minimum_score: 1,
          cooldown_seconds: 0
        }
      },
      channelCooldownSeconds: 0,
      windowSeconds: 600,
      maxRepliesPerWindow: 10,
      minimumMargin: 2
    });
  });

  it("prefers a persisted Portal profile over the Railway JSON fallback", () => {
    const mia = deployment("mia", "card-mia", "Mia", {
      enabled: true,
      style: "quiet",
      topics: ["logic gap"],
      trigger_phrases: ["are you serious"]
    });

    const envOnlyMessage = evaluateSmartParticipation(
      [mia],
      "legacy-env-keyword",
      1_000_000
    );
    expect(envOnlyMessage.reason).toBe("below_threshold");

    const portalMessage = evaluateSmartParticipation(
      [mia],
      "This logic gap is obvious, are you serious?",
      1_001_000
    );
    expect(portalMessage.reason).toBe("selected");
    expect(portalMessage.candidates[0]?.minimumScore).toBe(6);
  });

  it("honors an explicitly disabled Portal profile instead of falling back to ENV", () => {
    const mia = deployment("mia", "card-mia", "Mia", {
      enabled: false,
      keywords: ["legacy-env-keyword"]
    });
    const result = evaluateSmartParticipation([mia], "legacy-env-keyword?", 1_000_000);

    expect(result.reason).toBe("below_threshold");
    expect(result.candidates[0]?.eligible).toBe(false);
    expect(result.candidates[0]?.signals.profile_disabled_blocked).toBe(1);
  });

  it("selects exactly one configured Secondary after its preferred Primary", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena",
      cooldown_seconds: 180
    });

    const result = evaluateSmartFollowUp(serena, [serena, mia], 1_000_000);
    expect(result.reason).toBe("selected");
    expect(result.selectedDeployment?.deployment_id).toBe("mia");

    const repeated = evaluateSmartFollowUp(serena, [serena, mia], 1_001_000);
    expect(repeated.reason).toBe("secondary_cooldown");
    expect(repeated.selectedDeployment).toBeNull();
  });

  it("does not chain a Secondary into another automatic follow-up", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const result = evaluateSmartFollowUp(mia, [serena, mia], 1_000_000);
    expect(result.reason).toBe("source_not_primary");
    expect(result.selectedDeployment).toBeNull();
  });

  it("stays silent when more than one Secondary claims the same Primary", () => {
    const serena = deployment("serena", "card-serena", "Serena", {
      group_role: "primary"
    });
    const mia = deployment("mia", "card-mia", "Mia", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });
    const zoe = deployment("zoe", "card-zoe", "Zoe", {
      group_role: "secondary",
      preferred_follow_up_character_card_id: "card-serena"
    });

    const result = evaluateSmartFollowUp(serena, [serena, mia, zoe], 1_000_000);
    expect(result.reason).toBe("ambiguous_secondary");
    expect(result.selectedDeployment).toBeNull();
  });
});