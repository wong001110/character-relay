export type TestKind =
  | "identity_integrity"
  | "false_memory"
  | "prompt_injection"
  | "long_conversation_drift";

export type TestLanguage = "en" | "zh-CN";
export type ObservationMode = "watch" | "fast";
export type TesterMode = "benchmark" | "adaptive";
export type JudgeMode = "rules" | "semantic" | "hybrid";
export type ProviderId = "deepseek" | "openai" | "openrouter" | "custom";
export type ReportFormat = "markdown" | "json";
export type RuntimeKind = "adaptive" | "judge";
export type AccountRole = "user" | "admin";

export interface AuthConfig {
  registration_enabled: boolean;
  invitation_required: boolean;
  authentication_required: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  role: AccountRole;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: AuthUser;
}

export interface AuthSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  current: boolean;
}

export interface InvitationView {
  id: string;
  email: string | null;
  role: AccountRole;
  created_by: string | null;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  status: "active" | "accepted" | "revoked" | "expired";
}

export interface InvitationCreated {
  invitation: InvitationView;
  code: string;
}

export interface AdminAccount {
  id: string;
  email: string;
  display_name: string;
  role: AccountRole;
  is_active: boolean;
  created_at: string;
}

export interface AuditEventPage {
  items: AuditEventView[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface AuditEventView {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface LifecycleResult {
  affected: Record<string, number>;
}

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

export interface CharacterCardUpdate
  extends Omit<CharacterCardCreate, "target_id"> {
  provider?: ProviderId;
  base_url?: string;
  model?: string;
  system_prompt?: string;
  temperature?: number;
}

export interface CharacterSuggestionRequest {
  concept: string;
  name_hint: string;
  relationship_context: string;
  writing_constraints: string;
  subject_type_hint: CharacterCard["subject_type"];
  language: "en" | "zh-CN";
}

export interface CharacterSuggestionResult {
  display_name: string;
  subtitle: string;
  subject_type: CharacterCard["subject_type"];
  persona_summary: string;
  traits: string[];
  tags: string[];
  expected_tone: string;
  forbidden_behaviors: string[];
  memory_summary: string;
  system_prompt: string;
  provider_model: string;
  correction_used: boolean;
}

export interface CredentialStatus {
  required: boolean;
  configured: boolean;
  source: "vault" | "memory" | "environment" | "not_required" | "missing";
}

export interface AdaptiveRuntimeProfile {
  enabled: boolean;
  provider: ProviderId;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  max_turns: number;
}

export interface JudgeRuntimeProfile {
  enabled: boolean;
  provider: ProviderId;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  rubric_version: string;
}

export interface AdminRuntimeConfig {
  adaptive: AdaptiveRuntimeProfile;
  judge: JudgeRuntimeProfile;
  default_judge_mode: JudgeMode;
}

export interface AgentRuntimeStatus {
  enabled: boolean;
  configured: boolean;
  provider: string;
  model: string;
  credential_source: "vault" | "memory" | "environment" | "missing";
}

export interface RuntimeStatus {
  admin_available: boolean;
  adaptive: AgentRuntimeStatus;
  judge: AgentRuntimeStatus;
  default_judge_mode: JudgeMode;
}

export interface AdminRuntimeView {
  config: AdminRuntimeConfig;
  status: RuntimeStatus;
}

export interface Evidence {
  code: string;
  message: string;
  turn_index: number;
  excerpt: string;
  severity: string;
}

export interface Verdict {
  passed: boolean;
  score: number;
  failure_type?: string | null;
  summary: string;
  severity: string;
  evidence: Evidence[];
}

export interface SemanticJudgeMetadata {
  provider: string;
  model: string;
  rubric_version: string;
  confidence: number;
  dimensions: Record<string, number>;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface TrialResult {
  scenario: {
    id: string;
    name: string;
    kind: TestKind;
    language: TestLanguage;
    expected_behavior: string;
  };
  turns: Array<{
    index: number;
    tester_message: string;
    target_response: string;
    latency_ms: number | null;
  }>;
  verdict: Verdict;
  breakpoint: number | null;
  judge_mode: JudgeMode;
  rule_verdict: Verdict | null;
  semantic_verdict: Verdict | null;
  semantic_metadata: SemanticJudgeMetadata | null;
  review_required: boolean;
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
    | "judge_thinking"
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
  suite: TestKind[];
  test_language: TestLanguage;
  tester_mode: TesterMode;
  judge_mode: JudgeMode;
  result: {
    average_score: number;
    passed: boolean;
    review_required: boolean;
    results: TrialResult[];
  } | null;
  error: string | null;
}

export interface TrialSnapshot {
  run: TrialRun;
  events: TrialEvent[];
}

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
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function requestText(url: string): Promise<string> {
  const response = await fetch(url, { credentials: "include" });
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
  getAuthConfig: () => request<AuthConfig>("/api/auth/config"),
  getCurrentUser: () => request<AuthUser>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  register: (
    email: string,
    displayName: string,
    password: string,
    invitationCode?: string
  ) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        display_name: displayName,
        password,
        invitation_code: invitationCode || null
      })
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  listSessions: () => request<AuthSession[]>("/api/auth/sessions"),
  revokeSession: (sessionId: string) =>
    request<void>(`/api/auth/sessions/${sessionId}`, { method: "DELETE" }),
  exportAccount: () => request<Record<string, unknown>>("/api/account/export"),
  deleteAccount: (email: string, confirmation: string) =>
    request<LifecycleResult>("/api/account", {
      method: "DELETE",
      body: JSON.stringify({ email, confirmation })
    }),
  listInvitations: () => request<InvitationView[]>("/api/admin/invitations"),
  createInvitation: (payload: {
    email: string | null;
    role: AccountRole;
    expires_in_days: number;
  }) =>
    request<InvitationCreated>("/api/admin/invitations", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  revokeInvitation: (invitationId: string) =>
    request<void>(`/api/admin/invitations/${invitationId}`, { method: "DELETE" }),
  listAdminUsers: () => request<AdminAccount[]>("/api/admin/users"),
  updateUserRole: (userId: string, role: AccountRole) =>
    request<AdminAccount>(`/api/admin/users/${userId}/role`, {
      method: "PUT",
      body: JSON.stringify({ role })
    }),
  listAuditEvents: () => request<AuditEventView[]>("/api/admin/audit"),
  listAuditEventsPage: (cursor: string | null = null, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<AuditEventPage>(`/api/admin/audit/page?${query.toString()}`);
  },
  claimLocalWorkspace: () =>
    request<LifecycleResult>("/api/admin/workspace/claim-local", {
      method: "POST",
      body: JSON.stringify({ confirmation: "CLAIM LOCAL WORKSPACE" })
    }),
  rotateCredentialVault: () =>
    request<{ rotated_count: number; key_version: string }>(
      "/api/admin/credentials/rotate",
      { method: "POST" }
    ),
  listTargets: () => request<TargetView[]>("/api/targets"),
  listCharacters: () => request<CharacterCard[]>("/api/characters"),
  suggestCharacter: (payload: CharacterSuggestionRequest) =>
    request<CharacterSuggestionResult>("/api/characters/suggest", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
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
  updateCharacter: (cardId: string, payload: CharacterCardUpdate) =>
    request<CharacterCard>(`/api/characters/${cardId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  getCredentialStatus: (cardId: string) =>
    request<CredentialStatus>(`/api/characters/${cardId}/credential`),
  configureCredential: (cardId: string, apiKey: string) =>
    request<CredentialStatus>(`/api/characters/${cardId}/credential`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey })
    }),
  getRuntimeStatus: () => request<RuntimeStatus>("/api/runtime/status"),
  getAdminRuntime: () => request<AdminRuntimeView>("/api/admin/runtime"),
  updateAdminRuntime: (config: AdminRuntimeConfig) =>
    request<AdminRuntimeView>("/api/admin/runtime", {
      method: "PUT",
      body: JSON.stringify(config)
    }),
  configureRuntimeCredential: (kind: RuntimeKind, apiKey: string) =>
    request<AdminRuntimeView>(`/api/admin/runtime/credentials/${kind}`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey })
    }),
  clearRuntimeCredential: (kind: RuntimeKind) =>
    request<AdminRuntimeView>(`/api/admin/runtime/credentials/${kind}`, {
      method: "DELETE"
    }),
  startTrial: (
    characterCardId: string,
    suite: TestKind[],
    mode: ObservationMode,
    testerMode: TesterMode,
    judgeMode: JudgeMode,
    testLanguage: TestLanguage
  ) =>
    request<TrialRun>("/api/trials", {
      method: "POST",
      body: JSON.stringify({
        character_card_id: characterCardId,
        suite,
        mode,
        tester_mode: testerMode,
        judge_mode: judgeMode,
        test_language: testLanguage
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
    throw new Error("Trial observation timed out.");
  }
};
