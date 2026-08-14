import { describe, expect, it } from "vitest";

import {
  drainSmartParticipationDecisionEvents,
  recordSmartParticipationDecision
} from "./behaviorDecisionTrace.js";
import { DiscordEventReporter } from "./eventReporter.js";
import type {
  SmartParticipationDecision,
  SmartParticipationSignals
} from "./smartParticipation.js";
import type { DiscordDeployment } from "./types.js";

function deployment(id: string, name: string): DiscordDeployment {
  return {
    deployment_id: id,
    connection_id: "connection-1",
    character_card_id: `card-${id}`,
    character_display_name: name,
    workspace_id: "guild-1",
    workspace_name: "Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    category_id: "",
    server_profile_id: "profile-1",
    channel_scope_mode: "exact",
    excluded_channel_ids: [],
    excluded_category_ids: [],
    participation_mode: "smart",
    version_label: "Current",
    status: "active",
    identity_mode: "webhook",
    identity_display_name: name,
    identity_avatar_url: "",
    webhook_status: "active",
    orchestration_mode: "character_turn"
  };
}

function signals(): SmartParticipationSignals {
  return {
    question: 2,
    help_request: 0,
    name_match: 0,
    topic_match: 3,
    keyword_match: 0,
    trigger_phrase: 0,
    semantic_match: 4,
    initiative: 0.45,
    short_message_penalty: 0,
    recent_turn_match: 0,
    lightweight_follow_up: 0,
    cooldown_blocked: 0,
    avoid_phrase_blocked: 0,
    profile_disabled_blocked: 0
  };
}

describe("Behavior decision trace", () => {
  it("uploads every smart candidate even when only one candidate was scored/selected", async () => {
    drainSmartParticipationDecisionEvents();
    const ann = deployment("ann", "Ann");
    const zhi = deployment("zhi", "Zhi");
    const decision = {
      reason: "selected",
      selectedDeployment: ann,
      selectedDeployments: [ann],
      turns: [],
      candidates: [
        {
          deployment: ann,
          score: 9.45,
          minimumScore: 5,
          eligible: true,
          semanticRelevance: 0.85,
          signals: signals(),
          matchedTopics: ["ai"],
          matchedKeywords: [],
          matchedTriggerPhrases: [],
          matchedAvoidPhrases: []
        }
      ]
    } as SmartParticipationDecision;

    recordSmartParticipationDecision({
      message: "LLM judge 应该怎么设计？",
      decision,
      deployments: [ann, zhi]
    });

    const delivered: Array<Array<{ event_type: string; details: Record<string, unknown> }>> = [];
    const reporter = new DiscordEventReporter(async (events) => {
      delivered.push(events);
    });
    await reporter.flush();

    const event = delivered[0]?.find((item) => item.event_type === "smart_participation_decision");
    expect(event).toBeTruthy();
    const candidates = event?.details.candidates as Array<Record<string, unknown>>;
    expect(candidates).toHaveLength(2);
    expect(candidates[0]?.character_name).toBe("Ann");
    expect(candidates[0]?.selected).toBe(true);
    expect(candidates[0]?.signals).toMatchObject({ semantic_match: 4, topic_match: 3 });
    expect(candidates[1]?.character_name).toBe("Zhi");
    expect(candidates[1]?.scored).toBe(false);
    expect(event?.details.trigger_preview).toContain("LLM judge");
  });
});
