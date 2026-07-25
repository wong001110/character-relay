export type TestKind =
  | "identity_integrity"
  | "false_memory"
  | "prompt_injection"
  | "long_conversation_drift";

export type ObservationMode = "watch" | "fast";
export type TesterMode = "benchmark" | "adaptive";
export type ProviderId = "deepseek" | "openai" | "openrouter" | "custom";
export type ReportFormat = "markdown" | "json";

export interface TargetView {
  id: string;
  name: string;
  target_kind: string;
  config: Record<string, unknown>;
  created_at?: string;
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

export interface PromptCharacterCreate
  extends Omit<CharacterCardCreate, "target_id"> {
  provider: ProviderId;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  api_key: string;
}

export interface AdaptiveTesterConfig {
  provider: ProviderId;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  max_turns: number;
  api_key: string;
}

export interface CredentialStatus {
  required: boolean;
  configured: boolean;
  source: "memory" | "environment" | "not_required" | "missing";
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
    | "tester_thinking"
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

export interface TrialSnapshot {
  run: TrialRun;
  events: TrialEvent[];
}

const userHeaders = { "X-Echo-User": "local-user" };

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve the raw server response below.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...userHeaders,
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function requestText(url: string): Promise<string> {
  const response = await fetch(url, { headers: userHeaders });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.text();
}

function mergeEvents(current: TrialEvent[], incoming: TrialEvent[]): TrialEvent[] {
  const known = new Set(current.map((item) => item.sequence));
  return [...current, ...incoming.filter((item) => !known.has(item.sequence))].sort(
    (left, right) => left.sequence - right.sequence
  );
}

export function pollIntervalForMode(mode: ObservationMode): number {
  return mode === "watch" ? 1200 : 450;
}

export const api = {
  listTargets: () => request<TargetView[]>("/api/targets"),
  listCharacters: () => request<CharacterCard[]>("/api/characters"),
  createCharacter: (payload: CharacterCardCreate) =>
    request<CharacterCard>("/api/characters", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createPromptCharacter: (payload: PromptCharacterCreate) =>
    request<CharacterCard>("/api/characters/prompt-model", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getCredentialStatus: (cardId: string) =>
    request<CredentialStatus>(`/api/characters/${cardId}/credential`),
  configureCredential: (cardId: string, apiKey: string) =>
    request<CredentialStatus>(`/api/characters/${cardId}/credential`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey })
    }),
  startTrial: (
    characterCardId: string,
    suite: TestKind[],
    mode: ObservationMode,
    testerMode: TesterMode,
    adaptiveTester?: AdaptiveTesterConfig
  ) =>
    request<TrialRun>("/api/trials", {
      method: "POST",
      body: JSON.stringify({
        character_card_id: characterCardId,
        suite,
        mode,
        tester_mode: testerMode,
        adaptive_tester: testerMode === "adaptive" ? adaptiveTester : undefined
      })
    }),
  getTrial: (id: string) => request<TrialRun>(`/api/trials/${id}`),
  getTrialEvents: (id: string, after = 0) =>
    request<TrialEvent[]>(`/api/trials/${id}/events?after=${after}`),
  getTrialSnapshot: (id: string, after = 0) =>
    request<TrialSnapshot>(`/api/trials/${id}/snapshot?after=${after}`),
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
  getReport: (id: string, format: ReportFormat) =>
    requestText(`/api/reports/trials/${id}?format=${format}`),
  reportUrl: (id: string, format: ReportFormat) =>
    `/api/reports/trials/${id}?format=${format}`,
  observeTrial: async (
    id: string,
    mode: ObservationMode,
    onEvents: (events: TrialEvent[]) => void,
    onRun: (run: TrialRun) => void
  ): Promise<TrialRun> => {
    let events: TrialEvent[] = [];
    let after = 0;
    const interval = pollIntervalForMode(mode);
    const deadline = Date.now() + 30 * 60 * 1000;

    while (Date.now() < deadline) {
      const snapshot = await api.getTrialSnapshot(id, after);
      if (snapshot.events.length > 0) {
        events = mergeEvents(events, snapshot.events);
        after = events[events.length - 1]?.sequence ?? after;
        onEvents(events);
      }
      onRun(snapshot.run);
      if (!["pending", "running"].includes(snapshot.run.status)) return snapshot.run;
      await new Promise((resolve) => window.setTimeout(resolve, interval));
    }
    throw new Error("The observation session exceeded the live viewing window.");
  }
};
