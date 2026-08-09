import { beforeEach, describe, expect, it } from "vitest";

import { resolveAudience, shouldSubmitMessage } from "./routing.js";
import {
  configureSmartParticipation,
  resetSmartParticipationState
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

function deployment(id: string, name: string, cardId: string): DiscordDeployment {
  return {
    deployment_id: id,
    connection_id: "connection-1",
    character_card_id: cardId,
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
    orchestration_mode: "off"
  };
}

const ann = deployment("deploy-ann", "Ann", "character-ann");
const zhi = deployment("deploy-zhi", "Zhi", "character-zhi");

function configure(): void {
  configureSmartParticipation({
    enabled: true,
    profiles: {
      "character-ann": {
        keywords: ["sad", "tired", "难过", "累"],
        minimum_score: 5,
        cooldown_seconds: 0
      },
      "character-zhi": {
        topics: ["discord deployment"],
        keywords: ["discord", "deployment", "api", "bug"],
        minimum_score: 5,
        cooldown_seconds: 0
      }
    },
    minimumMargin: 2,
    channelCooldownSeconds: 0,
    windowSeconds: 600,
    maxRepliesPerWindow: 10
  });
}

describe("Smart Participation routing integration", () => {
  beforeEach(() => {
    resetSmartParticipationState();
    configure();
  });

  it("selects one Smart deployment before the provider call", () => {
    const audience = resolveAudience(
      [ann, zhi],
      "为什么 Discord deployment 的 API 没反应？"
    );

    expect(audience.reason).toBe("selected_smart");
    expect(audience.deployments.map((item) => item.deployment_id)).toEqual([
      zhi.deployment_id
    ]);
    expect(
      shouldSubmitMessage(
        audience.deployments[0]!,
        { mentionedBot: false, repliedToBot: false, hasReadableText: true },
        true
      )
    ).toBe(true);
  });

  it("keeps an ordinary low-information message silent", () => {
    const audience = resolveAudience([zhi], "好的");

    expect(audience.reason).toBe("selected_single");
    expect(
      shouldSubmitMessage(
        audience.deployments[0]!,
        { mentionedBot: false, repliedToBot: false, hasReadableText: true },
        true
      )
    ).toBe(false);
  });

  it("preserves explicit Mention behavior even when the deterministic gate is silent", () => {
    const audience = resolveAudience([zhi], "好的");

    expect(
      shouldSubmitMessage(
        audience.deployments[0]!,
        { mentionedBot: true, repliedToBot: false, hasReadableText: true },
        true
      )
    ).toBe(true);
  });

  it("preserves explicit character addressing", () => {
    const audience = resolveAudience([ann, zhi], "Ann, are you there?");

    expect(audience.reason).toBe("selected_alias");
    expect(audience.deployments[0]?.deployment_id).toBe(ann.deployment_id);
    expect(
      shouldSubmitMessage(
        audience.deployments[0]!,
        { mentionedBot: false, repliedToBot: false, hasReadableText: true },
        true
      )
    ).toBe(true);
  });

  it("retains ambiguity when no Smart character qualifies", () => {
    const audience = resolveAudience([ann, zhi], "好的");

    expect(audience.reason).toBe("ambiguous");
    expect(audience.deployments).toEqual([]);
  });
});
