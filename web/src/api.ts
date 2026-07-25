export type TestKind =
  | "identity_integrity"
  | "false_memory"
  | "prompt_injection"
  | "long_conversation_drift";

export type ObservationMode = "watch" | "fast";

export interface TargetView {
  id: string;
  name: string;
  target_kind: string;
}

export interface CharacterCard {
  id: string;
  owner_id: string;
  target_id: string;
  display_name: string;
  subtitle: string;
  subject_type: "companion" | "npc" | "assistant" | "custom";
  persona_summary: string;
  traits: string[];
  tags: string[];
  expected_tone: string | null;
  forbidden_behaviors: string[];
  memory_summary: string | null;
  preferred_suites: TestKind[];
  portrait_variant: "lavender" | "rose" | "mint" | "night";
  created_at: string;
}

export interface CharacterCardCreate {
  target_id: string;
  display_name: string;
  subtitle: string;
  subject_type: CharacterCard["subject_type"];
  persona_summary: string;
  traits: string[];
  tags: string[];
  expected_tone: string | null;
  forbidden_behaviors: string[];
  memory_summary: string | null;
  preferred_suites: TestKind[];
  portrait_variant: CharacterCard["portrait_variant"];
}

export interface Evidence {
  code: string;
  message: string;
  turn_index: number;
  excerpt: string;
  severity: string;
}

export interface TrialResult {
  scenario: { id: string; name: string; kind: TestKind; expected_behavior: string };
  turns: Array<{
    index: number;
    tester_message: string;
    target_response: string;
    latency_ms: number | null;
  }>;
  verdict: {
    passed: boolean;
    score: number;
    summary: string;
    severity: string;
    evidence: Evidence[];
  };
  breakpoint: number | null;
}

export interface TrialEvent {
  sequence: number;
  event_type:
    | "session_started"
    | "scenario_started"
    | "tester_message"
    | "subject_typing"
    | "subject_response"
    | "judge_result"
    | "breakpoint_detected"
    | "scenario_completed"
    | "session_completed"
    | "session_failed"
    | "session_cancelled";
  scenario_id: string | null;
  turn_index: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ComparisonResult {
  baseline_score: number;
  candidate_score: number;
  score_delta: number;
  baseline_average_latency_ms: number;
  candidate_average_latency_ms: number;
  latency_change_percent: number;
  baseline_total_tokens: number;
  candidate_total_tokens: number;
  token_delta: number;
  new_failures: string[];
  resolved_failures: string[];
  gate_passed: boolean;
  gate_violations: string[];
}

export interface TrialRun {
  id: string;
  target_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  result: { average_score: number; results: TrialResult[] } | null;
  error: string | null;
}

const userHeaders = { "X-Echo-User": "local-user" };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...userHeaders,
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function mergeEvents(current: TrialEvent[], incoming: TrialEvent[]): TrialEvent[] {
  const known = new Set(current.map((item) => item.sequence));
  return [...current, ...incoming.filter((item) => !known.has(item.sequence))].sort(
    (left, right) => left.sequence - right.sequence
  );
}

export const api = {
  listTargets: () => request<TargetView[]>("/api/targets"),
  listCharacters: () => request<CharacterCard[]>("/api/characters"),
  createCharacter: (payload: CharacterCardCreate) =>
    request<CharacterCard>("/api/characters", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  startTrial: (characterCardId: string, suite: TestKind[], mode: ObservationMode) =>
    request<TrialRun>("/api/trials", {
      method: "POST",
      body: JSON.stringify({ character_card_id: characterCardId, suite, mode })
    }),
  getTrial: (id: string) => request<TrialRun>(`/api/trials/${id}`),
  getTrialEvents: (id: string, after = 0) =>
    request<TrialEvent[]>(`/api/trials/${id}/events?after=${after}`),
  cancelTrial: (id: string) =>
    request<TrialRun>(`/api/trials/${id}/cancel`, { method: "POST" }),
  compareRuns: (baselineRunId: string, candidateRunId: string) =>
    request<ComparisonResult>("/api/comparisons", {
      method: "POST",
      body: JSON.stringify({
        baseline_run_id: baselineRunId,
        candidate_run_id: candidateRunId
      })
    }),
  reportUrl: (id: string, format: "markdown" | "json") =>
    `/api/reports/trials/${id}?format=${format}`,
  observeTrial: async (
    id: string,
    onEvents: (events: TrialEvent[]) => void,
    onRun: (run: TrialRun) => void
  ): Promise<TrialRun> => {
    let events: TrialEvent[] = [];
    let after = 0;
    for (let attempt = 0; attempt < 480; attempt += 1) {
      const incoming = await api.getTrialEvents(id, after);
      if (incoming.length > 0) {
        events = mergeEvents(events, incoming);
        after = events[events.length - 1]?.sequence ?? after;
        onEvents(events);
      }
      const run = await api.getTrial(id);
      onRun(run);
      if (!["pending", "running"].includes(run.status)) return run;
      await new Promise((resolve) => window.setTimeout(resolve, 180));
    }
    throw new Error("The observation session exceeded the live viewing window.");
  }
};
