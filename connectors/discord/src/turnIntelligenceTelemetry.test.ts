import { describe, expect, it } from "vitest";

import {
  CharacterContextTurnIntelligenceMetrics,
  hasCharacterContextTurnIntelligenceActivity,
  readCharacterContextTurnIntelligenceTrace
} from "./turnIntelligenceTelemetry.js";

describe("Character context Turn Intelligence telemetry", () => {
  it("treats legacy traces as inactive without throwing", () => {
    const trace = readCharacterContextTurnIntelligenceTrace({ rag_status: "completed" });
    expect(trace).toEqual({
      mode: "off",
      requestedTasks: [],
      knowledgeSource: "",
      pendingActionSource: "",
      knowledgeRoute: "",
      pendingActionContinue: null
    });
    expect(hasCharacterContextTurnIntelligenceActivity(trace)).toBe(false);
  });

  it("normalizes bounded trace fields", () => {
    const trace = readCharacterContextTurnIntelligenceTrace({
      turn_intelligence_mode: "active",
      turn_intelligence_requested_tasks: ["knowledge", "pending_action", "knowledge", 123],
      turn_intelligence_knowledge_source: "turn_intelligence",
      turn_intelligence_pending_action_source: "legacy_fallback",
      turn_intelligence_knowledge_route: "contextual",
      turn_intelligence_pending_action_continue: false
    });
    expect(trace).toEqual({
      mode: "active",
      requestedTasks: ["knowledge", "pending_action"],
      knowledgeSource: "turn_intelligence",
      pendingActionSource: "legacy_fallback",
      knowledgeRoute: "contextual",
      pendingActionContinue: false
    });
    expect(hasCharacterContextTurnIntelligenceActivity(trace)).toBe(true);
  });

  it("counts logical requested turns and per-field fallback separately", () => {
    const metrics = new CharacterContextTurnIntelligenceMetrics();
    metrics.observe(
      {
        turn_intelligence_mode: "active",
        turn_intelligence_requested_tasks: ["knowledge", "pending_action"],
        turn_intelligence_knowledge_source: "turn_intelligence",
        turn_intelligence_pending_action_source: "legacy_fallback",
        turn_intelligence_knowledge_route: "current",
        turn_intelligence_pending_action_continue: null
      },
      "2026-08-14T22:00:00.000Z"
    );
    metrics.observe(
      {
        turn_intelligence_mode: "shadow",
        turn_intelligence_requested_tasks: ["knowledge"],
        turn_intelligence_knowledge_source: "legacy_shadow",
        turn_intelligence_pending_action_source: "not_requested"
      },
      "2026-08-14T22:01:00.000Z"
    );
    metrics.observe({ turn_intelligence_mode: "off" });

    expect(metrics.healthSnapshot()).toEqual({
      character_context_turn_intelligence_observations: 2,
      character_context_turn_intelligence_requested_turns: 2,
      character_context_turn_intelligence_requested_tasks: 3,
      character_context_turn_intelligence_knowledge_applied: 1,
      character_context_turn_intelligence_pending_action_applied: 0,
      character_context_turn_intelligence_knowledge_legacy_fallbacks: 0,
      character_context_turn_intelligence_pending_action_legacy_fallbacks: 1,
      character_context_turn_intelligence_last_mode: "shadow",
      character_context_turn_intelligence_last_at: "2026-08-14T22:01:00.000Z",
      character_context_turn_intelligence_last_knowledge_source: "legacy_shadow",
      character_context_turn_intelligence_last_pending_action_source: "not_requested"
    });
  });
});