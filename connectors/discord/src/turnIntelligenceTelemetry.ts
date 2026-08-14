export interface CharacterContextTurnIntelligenceTrace {
  mode: string;
  requestedTasks: string[];
  knowledgeSource: string;
  pendingActionSource: string;
  knowledgeRoute: string;
  pendingActionContinue: boolean | null;
}

export interface CharacterContextTurnIntelligenceHealth {
  character_context_turn_intelligence_observations: number;
  character_context_turn_intelligence_requested_turns: number;
  character_context_turn_intelligence_requested_tasks: number;
  character_context_turn_intelligence_knowledge_applied: number;
  character_context_turn_intelligence_pending_action_applied: number;
  character_context_turn_intelligence_knowledge_legacy_fallbacks: number;
  character_context_turn_intelligence_pending_action_legacy_fallbacks: number;
  character_context_turn_intelligence_last_mode: string | null;
  character_context_turn_intelligence_last_at: string | null;
  character_context_turn_intelligence_last_knowledge_source: string | null;
  character_context_turn_intelligence_last_pending_action_source: string | null;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is string => typeof item === "string").map((item) => item.trim()).filter(Boolean))];
}

export function readCharacterContextTurnIntelligenceTrace(
  value: unknown
): CharacterContextTurnIntelligenceTrace {
  const source = record(value);
  const pending = source.turn_intelligence_pending_action_continue;
  return {
    mode: stringValue(source.turn_intelligence_mode) || "off",
    requestedTasks: stringArray(source.turn_intelligence_requested_tasks),
    knowledgeSource: stringValue(source.turn_intelligence_knowledge_source),
    pendingActionSource: stringValue(source.turn_intelligence_pending_action_source),
    knowledgeRoute: stringValue(source.turn_intelligence_knowledge_route),
    pendingActionContinue: typeof pending === "boolean" ? pending : null
  };
}

export function hasCharacterContextTurnIntelligenceActivity(
  value: CharacterContextTurnIntelligenceTrace
): boolean {
  return value.mode !== "off" || value.requestedTasks.length > 0;
}

export class CharacterContextTurnIntelligenceMetrics {
  private observations = 0;
  private requestedTurns = 0;
  private requestedTasks = 0;
  private knowledgeApplied = 0;
  private pendingApplied = 0;
  private knowledgeLegacyFallbacks = 0;
  private pendingLegacyFallbacks = 0;
  private lastMode: string | null = null;
  private lastAt: string | null = null;
  private lastKnowledgeSource: string | null = null;
  private lastPendingActionSource: string | null = null;

  observe(value: unknown, observedAt = new Date().toISOString()): CharacterContextTurnIntelligenceTrace {
    const trace = readCharacterContextTurnIntelligenceTrace(value);
    if (!hasCharacterContextTurnIntelligenceActivity(trace)) return trace;

    this.observations += 1;
    if (trace.requestedTasks.length > 0) {
      this.requestedTurns += 1;
      this.requestedTasks += trace.requestedTasks.length;
    }
    if (trace.knowledgeSource === "turn_intelligence") this.knowledgeApplied += 1;
    if (trace.pendingActionSource === "turn_intelligence") this.pendingApplied += 1;
    if (trace.knowledgeSource === "legacy_fallback") this.knowledgeLegacyFallbacks += 1;
    if (trace.pendingActionSource === "legacy_fallback") this.pendingLegacyFallbacks += 1;
    this.lastMode = trace.mode;
    this.lastAt = observedAt;
    this.lastKnowledgeSource = trace.knowledgeSource || null;
    this.lastPendingActionSource = trace.pendingActionSource || null;
    return trace;
  }

  healthSnapshot(): CharacterContextTurnIntelligenceHealth {
    return {
      character_context_turn_intelligence_observations: this.observations,
      character_context_turn_intelligence_requested_turns: this.requestedTurns,
      character_context_turn_intelligence_requested_tasks: this.requestedTasks,
      character_context_turn_intelligence_knowledge_applied: this.knowledgeApplied,
      character_context_turn_intelligence_pending_action_applied: this.pendingApplied,
      character_context_turn_intelligence_knowledge_legacy_fallbacks: this.knowledgeLegacyFallbacks,
      character_context_turn_intelligence_pending_action_legacy_fallbacks: this.pendingLegacyFallbacks,
      character_context_turn_intelligence_last_mode: this.lastMode,
      character_context_turn_intelligence_last_at: this.lastAt,
      character_context_turn_intelligence_last_knowledge_source: this.lastKnowledgeSource,
      character_context_turn_intelligence_last_pending_action_source: this.lastPendingActionSource
    };
  }
}
