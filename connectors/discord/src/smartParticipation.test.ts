import { beforeEach, describe, expect, it } from "vitest";

import {
  configureSmartParticipation,
  consumeSmartSelection,
  coordinateExplicitSmartParticipants,
  evaluateSmartParticipation,
  markExplicitSmartSelections,
  parseSmartParticipationProfiles,
  resetSmartParticipationState,
  restoreDurableLightweightSelection
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

function deployment(
  id: string,
  name: string,
  characterCardId: string,
  overrides: Partial<DiscordDeployment> = {}
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
    address_aliases: [],
    webhook_status: "pending",
    webhook_id: null,
    webhook_token: null,
    orchestration_mode: "off",
    ...overrides
  };
}

const zhi = deployment("deploy-zhi", "织 · Zhi", "character-zhi", {
  address_aliases: ["织", "Zhi"]
});
const ann = deployment("deploy-ann", "安 · Ann", "character-ann", {
  address_aliases: ["安", "Ann"]
});

function configure(overrides: Parameters<typeof configureSmartParticipation>[0] = {}): void {
  configureSmartParticipation({
    enabled: true,
    profiles: {
      "character-zhi": {
        topics: ["discord deployment", "software development", "rag"],
        keywords: ["discord", "deploy", "deployment", "api", "bug"],
        trigger_phrases: ["why", "怎么", "为什么", "有人知道"],
        avoid_phrases: ["不用回答", "just documenting"],
        initiative: 0.5,
        minimum_score: 5,
        cooldown_seconds: 120
      },
      "character-ann": {
        topics: ["daily life", "emotional support"],
        keywords: ["tired", "sad", "累", "难过"],
        initiative: 0.3,
        minimum_score: 5,
        cooldown_seconds: 120
      }
    },
    minimumMargin: 2,
    maxParticipants: 2,
    channelCooldownSeconds: 45,
    windowSeconds: 600,
    maxRepliesPerWindow: 3,
    lightweightFollowUpWindowSeconds: 90,
    ...overrides
  });
}

describe("deterministic Smart Participation", () => {
  beforeEach(() => {
    resetSmartParticipationState();
  });

  it("parses connector profile JSON", () => {
    expect(
      parseSmartParticipationProfiles(
        JSON.stringify({
          "character-zhi": {
            topics: ["RAG", "Discord"],
            initiative: 0.5,
            minimum_score: 5
          }
        })
      )
    ).toEqual({
      "character-zhi": {
        topics: ["RAG", "Discord"],
        initiative: 0.5,
        minimum_score: 5
      }
    });
  });

  it("rejects malformed profile JSON", () => {
    expect(() => parseSmartParticipationProfiles("[]")).toThrow(
      "must be a JSON object"
    );
    expect(() =>
      parseSmartParticipationProfiles(
        JSON.stringify({ "character-zhi": { topics: "RAG" } })
      )
    ).toThrow("topics must be an array of strings");
  });

  it("selects the strongest relevant character and exposes scoring signals", () => {
    configure();
    const result = evaluateSmartParticipation(
      [ann, zhi],
      "有人知道为什么 Discord deployment 没反应吗？",
      1_000_000
    );

    expect(result.reason).toBe("selected");
    expect(result.selectedDeployment?.deployment_id).toBe(zhi.deployment_id);
    expect(result.selectedDeployments.map((item) => item.deployment_id)).toEqual([
      zhi.deployment_id
    ]);
    expect(result.candidates[0]?.signals.question).toBe(2);
    expect(result.candidates[0]?.signals.help_request).toBe(2);
    expect(result.candidates[0]?.matchedKeywords).toContain("discord");
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(true);
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(false);
  });

  it("uses semantic Character Card relevance without manual topic or keyword matches", () => {
    configure({
      profiles: {
        "character-zhi": {
          initiative: 0.5,
          minimum_score: 4,
          cooldown_seconds: 0
        },
        "character-ann": {
          initiative: 0.3,
          minimum_score: 4,
          cooldown_seconds: 0
        }
      }
    });

    const result = evaluateSmartParticipation(
      [ann, zhi],
      "How should I turn several AI tools into a practical product workflow?",
      1_000_000,
      {
        [zhi.deployment_id]: 0.91,
        [ann.deployment_id]: 0.72
      }
    );

    expect(result.reason).toBe("selected");
    expect(result.selectedDeployment?.deployment_id).toBe(zhi.deployment_id);
    expect(result.candidates[0]?.semanticRelevance).toBe(0.91);
    expect(result.candidates[0]?.signals.semantic_match).toBe(6);
  });

  it("admits two strong character-specific candidates instead of forcing one winner", () => {
    configure({
      profiles: {
        "character-zhi": {
          initiative: 0.5,
          minimum_score: 4,
          cooldown_seconds: 0
        },
        "character-ann": {
          initiative: 0.5,
          minimum_score: 4,
          cooldown_seconds: 0
        }
      },
      minimumMargin: 2,
      maxParticipants: 2
    });

    const result = evaluateSmartParticipation(
      [ann, zhi],
      "Can you both help me reason about this AI product decision?",
      1_000_000,
      {
        [zhi.deployment_id]: 0.91,
        [ann.deployment_id]: 0.89
      }
    );

    expect(result.reason).toBe("selected_multiple");
    expect(result.selectedDeployments.map((item) => item.deployment_id)).toEqual([
      zhi.deployment_id,
      ann.deployment_id
    ]);
    expect(result.turns.map((item) => item.role)).toEqual(["primary", "complement"]);
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(true);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
  });

  it("does not add a generic runner-up without a character-specific reason", () => {
    configure({
      profiles: {
        "character-zhi": {
          initiative: 0.5,
          minimum_score: 4,
          cooldown_seconds: 0
        },
        "character-ann": {
          initiative: 0.5,
          minimum_score: 2,
          cooldown_seconds: 0
        }
      },
      minimumMargin: 6
    });

    const result = evaluateSmartParticipation(
      [ann, zhi],
      "How should I design this AI workflow?",
      1_000_000,
      { [zhi.deployment_id]: 0.91 }
    );

    expect(result.reason).toBe("selected");
    expect(result.selectedDeployments.map((item) => item.deployment_id)).toEqual([
      zhi.deployment_id
    ]);
  });

  it("coordinates one linked secondary before an explicitly addressed primary", () => {
    const lady = deployment("deploy-lady", "Serena", "character-lady");
    const attendant = deployment("deploy-attendant", "Mira", "character-attendant");
    configure({
      profiles: {
        "character-lady": {
          group_role: "primary",
          initiative: 0.4,
          minimum_score: 4,
          cooldown_seconds: 0
        },
        "character-attendant": {
          group_role: "secondary",
          preferred_follow_up_character_card_id: "character-lady",
          initiative: 0.5,
          minimum_score: 4,
          cooldown_seconds: 0
        }
      }
    });

    const result = coordinateExplicitSmartParticipants(
      [lady, attendant],
      [lady],
      "Why did you leave yesterday?",
      1_000_000,
      { [attendant.deployment_id]: 0.86 }
    );

    expect(result.coordinated).toBe(true);
    expect(result.deployments.map((item) => item.deployment_id)).toEqual([
      attendant.deployment_id,
      lady.deployment_id
    ]);
    expect(result.turns.map((item) => item.role)).toEqual(["interject", "primary"]);
    expect(consumeSmartSelection(attendant.deployment_id)).toBe(true);
    expect(consumeSmartSelection(lady.deployment_id)).toBe(true);
  });

  it("keeps low-information messages silent when no recent character turn exists", () => {
    configure();
    const result = evaluateSmartParticipation([ann, zhi], "好的", 1_000_000);

    expect(result.reason).toBe("low_information_message");
    expect(result.selectedDeployment).toBeNull();
  });

  it("allows one lightweight follow-up for the most recently admitted character turn", () => {
    configure();
    markExplicitSmartSelections([ann], 1_000_000);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    const result = evaluateSmartParticipation([ann, zhi], "哈哈", 1_010_000);

    expect(result.reason).toBe("selected_lightweight");
    expect(result.selectedDeployment?.deployment_id).toBe(ann.deployment_id);
    expect(result.candidates[0]?.signals.recent_turn_match).toBe(6);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
  });

  it("allows an Emoji-only acknowledgement as a lightweight follow-up", () => {
    configure();
    markExplicitSmartSelections([ann], 1_000_000);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    const result = evaluateSmartParticipation([ann, zhi], "😂", 1_010_000);
    expect(result.reason).toBe("selected_lightweight");
    expect(result.selectedDeployment?.deployment_id).toBe(ann.deployment_id);
  });

  it("does not chain repeated lightweight turns without a new substantive turn", () => {
    configure();
    markExplicitSmartSelections([ann], 1_000_000);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
    expect(
      evaluateSmartParticipation([ann, zhi], "哈哈", 1_010_000).reason
    ).toBe("selected_lightweight");
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);

    const second = evaluateSmartParticipation([ann, zhi], "lol", 1_020_000);
    expect(second.reason).toBe("low_information_message");
    expect(second.selectedDeployment).toBeNull();
  });

  it("stays silent when every candidate is below its threshold", () => {
    configure();
    const result = evaluateSmartParticipation(
      [ann, zhi],
      "今天频道很安静。",
      1_000_000
    );

    expect(result.reason).toBe("below_threshold");
    expect(result.selectedDeployment).toBeNull();
  });

  it("allows tied meaningful characters to participate together", () => {
    configure({
      profiles: {
        "character-zhi": {
          topics: ["project"],
          minimum_score: 2,
          cooldown_seconds: 0
        },
        "character-ann": {
          topics: ["project"],
          minimum_score: 2,
          cooldown_seconds: 0
        }
      },
      minimumMargin: 2,
      maxParticipants: 2
    });
    const result = evaluateSmartParticipation(
      [ann, zhi],
      "这个 project 应该怎么继续？",
      1_000_000
    );

    expect(result.reason).toBe("selected_multiple");
    expect(result.selectedDeployments).toHaveLength(2);
  });

  it("respects avoid phrases before scoring", () => {
    configure();
    const result = evaluateSmartParticipation(
      [zhi],
      "Discord deployment 还是没反应，不过不用回答，我只是记录一下。",
      1_000_000
    );

    expect(result.reason).toBe("below_threshold");
    expect(result.candidates[0]?.eligible).toBe(false);
    expect(result.candidates[0]?.signals.avoid_phrase_blocked).toBe(1);
  });

  it("starts channel cooldown only after the selected Smart turn is admitted", () => {
    configure();
    const first = evaluateSmartParticipation(
      [zhi],
      "为什么 Discord deployment 没反应？",
      1_000_000
    );
    expect(first.reason).toBe("selected");
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(true);

    const second = evaluateSmartParticipation(
      [zhi],
      "另一个 Discord bug 怎么解决？",
      1_010_000
    );
    expect(second.reason).toBe("channel_cooldown");
  });

  it("does not consume cooldown merely because a candidate was evaluated", () => {
    configure();
    expect(
      evaluateSmartParticipation(
        [zhi],
        "为什么 Discord deployment 没反应？",
        1_000_000
      ).reason
    ).toBe("selected");

    const second = evaluateSmartParticipation(
      [zhi],
      "另一个 Discord bug 怎么解决？",
      1_010_000
    );
    expect(second.reason).toBe("selected");
  });

  it("enforces a per-channel proactive turn limit after admitted turns", () => {
    configure({
      channelCooldownSeconds: 0,
      windowSeconds: 600,
      maxRepliesPerWindow: 2,
      profiles: {
        "character-zhi": {
          keywords: ["discord"],
          minimum_score: 2,
          cooldown_seconds: 0
        }
      }
    });

    expect(
      evaluateSmartParticipation([zhi], "Discord issue one?", 1_000_000).reason
    ).toBe("selected");
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(true);
    expect(
      evaluateSmartParticipation([zhi], "Discord issue two?", 1_001_000).reason
    ).toBe("selected");
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(true);
    expect(
      evaluateSmartParticipation([zhi], "Discord issue three?", 1_002_000).reason
    ).toBe("channel_rate_limit");
  });

  it("marks explicitly addressed Smart deployments without counting a proactive decision", () => {
    configure();
    markExplicitSmartSelections([ann], 1_000_000);

    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
    const result = evaluateSmartParticipation(
      [ann],
      "我今天很累也很难过，可以帮我吗？",
      1_001_000
    );
    expect(result.reason).toBe("selected");
  });

  it("does not select candidates while the runtime is disabled", () => {
    configureSmartParticipation({ enabled: false });
    const result = evaluateSmartParticipation(
      [zhi],
      "为什么 Discord deployment 没反应？",
      1_000_000
    );

    expect(result.reason).toBe("disabled");
    expect(consumeSmartSelection(zhi.deployment_id)).toBe(false);
  });
});


describe("durable lightweight recovery", () => {
  beforeEach(() => {
    resetSmartParticipationState();
  });

  it("rehydrates a server-proven recent Smart speaker into the normal local admission path", () => {
    configure({
      profiles: {
        "character-ann": {
          initiative: 0.3,
          minimum_score: 5,
          cooldown_seconds: 0
        }
      }
    });
    const result = restoreDurableLightweightSelection(
      [ann, zhi],
      ann.deployment_id,
      "嗯",
      1_000_000,
      "connection-1:guild-1:channel-1:"
    );

    expect(result.reason).toBe("selected_lightweight");
    expect(result.selectedDeployment?.deployment_id).toBe(ann.deployment_id);
    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);
    expect(
      evaluateSmartParticipation(
        [ann, zhi],
        "哈哈",
        1_001_000,
        {},
        "connection-1:guild-1:channel-1:"
      ).reason
    ).toBe("low_information_message");
  });

  it("does not restore a Character blocked by its avoid phrase", () => {
    configure({
      profiles: {
        "character-ann": {
          avoid_phrases: ["嗯"],
          initiative: 0.3,
          minimum_score: 5,
          cooldown_seconds: 0
        }
      }
    });
    const result = restoreDurableLightweightSelection(
      [ann],
      ann.deployment_id,
      "嗯",
      1_000_000
    );
    expect(result.selectedDeployment).toBeNull();
  });
});
