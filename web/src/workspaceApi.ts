import type {
  CharacterCard,
  JudgeMode,
  ObservationMode,
  TestKind,
  TestLanguage,
  TesterMode,
  TrialRun
} from "./api";

export type ScenarioSeverity = "info" | "low" | "medium" | "high" | "critical";
export type MatrixStatus = "draft" | "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";
export type MatrixTaskStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface ScenarioFields {
  name: string;
  category: TestKind;
  description: string;
  language: TestLanguage;
  messages: string[];
  expected_behavior: string;
  forbidden_phrases: string[];
  required_phrases: string[];
  severity: ScenarioSeverity;
  max_turns: number;
  recommended_tester_mode: TesterMode;
  recommended_judge_mode: JudgeMode;
}

export interface ScenarioView extends ScenarioFields {
  id: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export interface PackItemInput {
  scenario_id: string;
  enabled: boolean;
}

export interface PackScenarioView {
  scenario: ScenarioView;
  position: number;
  enabled: boolean;
}

export interface TestPackView {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  version: number;
  items: PackScenarioView[];
  created_at: string;
  updated_at: string;
}

export interface TestPackFields {
  name: string;
  description: string;
  items: PackItemInput[];
}

export interface ExperimentHistoryItem {
  run_id: string;
  status: string;
  character_card_id: string | null;
  character_name: string;
  test_pack_id: string | null;
  test_pack_name: string | null;
  test_language: TestLanguage;
  tester_mode: TesterMode;
  judge_mode: JudgeMode;
  score: number | null;
  passed: boolean | null;
  review_required: boolean;
  is_baseline: boolean;
  rerun_of: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExperimentHistoryPage {
  items: ExperimentHistoryItem[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface RunSnapshotView {
  run_id: string;
  owner_id: string;
  character_card_id: string | null;
  test_pack_id: string | null;
  character: Record<string, unknown>;
  target: Record<string, unknown>;
  test_pack: Record<string, unknown>;
  scenarios: Array<Record<string, unknown>>;
  rerun_of: string | null;
  is_baseline: boolean;
  created_at: string;
}

export interface StorageDiagnostics {
  environment: string;
  database_url_redacted: string;
  database_kind: string;
  database_path: string | null;
  writable: boolean;
  persistent_path_expected: boolean;
  persistent_path_configured: boolean;
  warning: string | null;
  character_count: number;
  scenario_count: number;
  pack_count: number;
  run_count: number;
  last_write_at: string | null;
}

export interface PersistenceProbeView {
  id: string;
  marker: string;
  created_at: string;
}

export interface WorkspaceArchive {
  schema_version: "1";
  exported_at: string;
  owner_id: string;
  targets: Array<Record<string, unknown>>;
  character_cards: Array<Record<string, unknown>>;
  scenarios: Array<Record<string, unknown>>;
  test_packs: Array<Record<string, unknown>>;
  trial_runs: Array<Record<string, unknown>>;
  character_trials: Array<Record<string, unknown>>;
  run_snapshots: Array<Record<string, unknown>>;
  turns: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown>>;
  admin_runtime: Record<string, unknown> | null;
}

export interface PromptVersionView {
  id: string;
  owner_id: string;
  character_card_id: string;
  version: number;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  config_hash: string;
  is_active: boolean;
  is_production: boolean;
  created_at: string;
}

export interface PromptVersionDiff {
  left: PromptVersionView;
  right: PromptVersionView;
  changed_fields: string[];
  system_prompt_before: string;
  system_prompt_after: string;
}

export interface MatrixSubjectSelection {
  character_card_id: string;
  prompt_version_ids: string[];
}

export interface MatrixDefinition {
  subjects: MatrixSubjectSelection[];
  model_overrides: string[];
  temperatures: number[];
  test_pack_ids: string[];
  test_languages: TestLanguage[];
  tester_modes: TesterMode[];
  judge_modes: JudgeMode[];
  repeat_count: number;
  concurrency: number;
  max_attempts: number;
}

export interface MatrixFields {
  name: string;
  description: string;
  definition: MatrixDefinition;
}

export interface MatrixPreview {
  task_count: number;
  maximum_task_count: number;
  within_limit: boolean;
  requires_adaptive: boolean;
  requires_semantic: boolean;
  subject_variants: number;
  model_variants: number;
  temperature_variants: number;
  pack_variants: number;
  language_variants: number;
  tester_variants: number;
  judge_variants: number;
  repeats: number;
}

export interface MatrixView {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  status: MatrixStatus;
  definition: MatrixDefinition;
  total_tasks: number;
  pending_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  cancelled_tasks: number;
  is_baseline: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface MatrixListPage {
  items: MatrixView[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface MatrixTaskCombination {
  character_card_id: string;
  prompt_version_id: string | null;
  model_override: string | null;
  temperature: number | null;
  test_pack_id: string;
  test_language: TestLanguage;
  tester_mode: TesterMode;
  judge_mode: JudgeMode;
  repeat_index: number;
}

export interface MatrixTaskView {
  id: string;
  matrix_id: string;
  ordinal: number;
  status: MatrixTaskStatus;
  combination: MatrixTaskCombination;
  run_id: string | null;
  attempt_count: number;
  max_attempts: number;
  retry_count: number;
  backoff_seconds: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface MatrixVariantAnalytics {
  key: string;
  label: string;
  run_count: number;
  mean_score: number | null;
  minimum_score: number | null;
  maximum_score: number | null;
  standard_deviation: number | null;
  pass_rate: number;
  review_rate: number;
  failure_rate: number;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

export interface MatrixAnalytics {
  matrix_id: string;
  matrix_name: string;
  status: MatrixStatus;
  total_tasks: number;
  completed_runs: number;
  failed_tasks: number;
  cancelled_tasks: number;
  mean_score: number | null;
  minimum_score: number | null;
  maximum_score: number | null;
  variance: number | null;
  standard_deviation: number | null;
  pass_rate: number;
  review_rate: number;
  failure_rate: number;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  provider_errors: number;
  retry_count: number;
  failure_types: Array<{ key: string; count: number }>;
  breakpoints: Array<{ key: string; count: number }>;
  scenarios: MatrixVariantAnalytics[];
  by_character: MatrixVariantAnalytics[];
  by_prompt_version: MatrixVariantAnalytics[];
  by_model: MatrixVariantAnalytics[];
  by_temperature: MatrixVariantAnalytics[];
  by_language: MatrixVariantAnalytics[];
  by_tester: MatrixVariantAnalytics[];
  by_judge: MatrixVariantAnalytics[];
}

export interface MatrixComparison {
  baseline: MatrixAnalytics;
  candidate: MatrixAnalytics;
  compatible: boolean;
  incompatibilities: string[];
  score_delta: number | null;
  pass_rate_delta: number;
  review_rate_delta: number;
  failure_rate_delta: number;
  latency_delta_ms: number;
  input_token_delta: number;
  output_token_delta: number;
  classification: "improved" | "no_meaningful_change" | "regression" | "incompatible";
}

const userHeaders = {
  "Content-Type": "application/json",
  "X-Echo-User": "local-user"
};

async function message(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const value = JSON.parse(raw) as { detail?: unknown };
    if (typeof value.detail === "string") return value.detail;
  } catch {
    // Use the raw body below.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { ...userHeaders, ...(init?.headers ?? {}) }
  });
  if (!response.ok) throw new Error(await message(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function adminHeaders(token: string): HeadersInit {
  return { "X-Echo-Admin": token };
}

export const workspaceApi = {
  listScenarios: () => request<ScenarioView[]>("/api/scenarios"),
  createScenario: (payload: ScenarioFields) =>
    request<ScenarioView>("/api/scenarios", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateScenario: (id: string, payload: ScenarioFields) =>
    request<ScenarioView>(`/api/scenarios/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  duplicateScenario: (id: string) =>
    request<ScenarioView>(`/api/scenarios/${id}/duplicate`, { method: "POST" }),
  deleteScenario: (id: string) =>
    request<void>(`/api/scenarios/${id}`, { method: "DELETE" }),

  listPacks: () => request<TestPackView[]>("/api/test-packs"),
  createPack: (payload: TestPackFields) =>
    request<TestPackView>("/api/test-packs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updatePack: (id: string, payload: TestPackFields) =>
    request<TestPackView>(`/api/test-packs/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  duplicatePack: (id: string) =>
    request<TestPackView>(`/api/test-packs/${id}/duplicate`, { method: "POST" }),
  deletePack: (id: string) =>
    request<void>(`/api/test-packs/${id}`, { method: "DELETE" }),

  startPackTrial: (
    card: CharacterCard,
    packId: string,
    mode: ObservationMode,
    testerMode: TesterMode,
    judgeMode: JudgeMode,
    language: TestLanguage
  ) =>
    request<TrialRun>("/api/trials", {
      method: "POST",
      body: JSON.stringify({
        character_card_id: card.id,
        test_pack_id: packId,
        suite: [],
        mode,
        tester_mode: testerMode,
        judge_mode: judgeMode,
        test_language: language
      })
    }),

  history: (params: URLSearchParams) =>
    request<ExperimentHistoryPage>(`/api/experiments?${params.toString()}`),
  snapshot: (runId: string) =>
    request<RunSnapshotView>(`/api/experiments/${runId}/snapshot`),
  setBaseline: (runId: string, value: boolean) =>
    request<RunSnapshotView>(`/api/experiments/${runId}/baseline?value=${value}`, {
      method: "PUT"
    }),
  rerun: (runId: string) =>
    request<{ run_id: string }>(`/api/experiments/${runId}/rerun`, {
      method: "POST"
    }),
  deleteExperiment: (runId: string) =>
    request<void>(`/api/experiments/${runId}`, { method: "DELETE" }),

  listPromptVersions: (cardId: string) =>
    request<PromptVersionView[]>(`/api/characters/${cardId}/prompt-versions`),
  restorePromptVersion: (cardId: string, versionId: string) =>
    request<PromptVersionView>(`/api/characters/${cardId}/prompt-versions/${versionId}/restore`, {
      method: "POST"
    }),
  setProductionPromptVersion: (cardId: string, versionId: string, value: boolean) =>
    request<PromptVersionView>(
      `/api/characters/${cardId}/prompt-versions/${versionId}/production?value=${value}`,
      { method: "PUT" }
    ),
  comparePromptVersions: (leftId: string, rightId: string) =>
    request<PromptVersionDiff>(
      `/api/prompt-versions/compare?left_id=${encodeURIComponent(leftId)}&right_id=${encodeURIComponent(rightId)}`
    ),

  previewMatrix: (definition: MatrixDefinition) =>
    request<MatrixPreview>("/api/matrices/preview", {
      method: "POST",
      body: JSON.stringify(definition)
    }),
  listMatrices: (page = 1) => request<MatrixListPage>(`/api/matrices?page=${page}`),
  createMatrix: (payload: MatrixFields) =>
    request<MatrixView>("/api/matrices", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateMatrix: (id: string, payload: MatrixFields) =>
    request<MatrixView>(`/api/matrices/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteMatrix: (id: string) => request<void>(`/api/matrices/${id}`, { method: "DELETE" }),
  launchMatrix: (id: string, confirmedTaskCount: number) =>
    request<MatrixView>(`/api/matrices/${id}/launch`, {
      method: "POST",
      body: JSON.stringify({ confirmed_task_count: confirmedTaskCount })
    }),
  pauseMatrix: (id: string) => request<MatrixView>(`/api/matrices/${id}/pause`, { method: "POST" }),
  resumeMatrix: (id: string) => request<MatrixView>(`/api/matrices/${id}/resume`, { method: "POST" }),
  cancelMatrix: (id: string) => request<MatrixView>(`/api/matrices/${id}/cancel`, { method: "POST" }),
  retryMatrix: (id: string) => request<MatrixView>(`/api/matrices/${id}/retry-failed`, { method: "POST" }),
  setMatrixBaseline: (id: string, value: boolean) =>
    request<MatrixView>(`/api/matrices/${id}/baseline?value=${value}`, { method: "PUT" }),
  matrixTasks: (id: string) => request<MatrixTaskView[]>(`/api/matrices/${id}/tasks`),
  matrixAnalytics: (id: string) => request<MatrixAnalytics>(`/api/matrices/${id}/analytics`),
  compareMatrices: (baselineId: string, candidateId: string) =>
    request<MatrixComparison>(
      `/api/matrices/compare/result?baseline_id=${encodeURIComponent(baselineId)}&candidate_id=${encodeURIComponent(candidateId)}`
    ),
  matrixExportUrl: (id: string, format: "json" | "csv" | "markdown") =>
    `/api/matrices/${id}/export?format=${format}`,

  storage: (adminToken: string) =>
    request<StorageDiagnostics>("/api/admin/storage", {
      headers: adminHeaders(adminToken)
    }),
  createProbe: (adminToken: string, marker: string) =>
    request<PersistenceProbeView>(
      `/api/admin/storage/probes?marker=${encodeURIComponent(marker)}`,
      { method: "POST", headers: adminHeaders(adminToken) }
    ),
  getProbe: (adminToken: string, id: string) =>
    request<PersistenceProbeView>(`/api/admin/storage/probes/${id}`, {
      headers: adminHeaders(adminToken)
    }),
  deleteProbe: (adminToken: string, id: string) =>
    request<void>(`/api/admin/storage/probes/${id}`, {
      method: "DELETE",
      headers: adminHeaders(adminToken)
    }),
  exportWorkspace: (adminToken: string) =>
    request<WorkspaceArchive>("/api/admin/workspace/export", {
      headers: adminHeaders(adminToken)
    }),
  importWorkspace: (
    adminToken: string,
    archive: WorkspaceArchive,
    mode: "merge" | "replace"
  ) =>
    request<{ imported: Record<string, number>; skipped: Record<string, number> }>(
      "/api/admin/workspace/import",
      {
        method: "POST",
        headers: adminHeaders(adminToken),
        body: JSON.stringify({ archive, mode })
      }
    )
};
