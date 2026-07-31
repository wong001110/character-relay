import type {
  CharacterCard,
  JudgeMode,
  ProviderId,
  TestKind,
  TestLanguage,
  TesterMode
} from "./api";

export type DraftStatus = "draft" | "approved" | "rejected";

export interface DraftProvenance {
  source: "manual" | "ai";
  character_card_id: string | null;
  source_model: string | null;
  prompt_hash: string | null;
  risk_tags: string[];
  generated_at: string | null;
}

export interface ScenarioDraftFields {
  name: string;
  category: TestKind;
  description: string;
  language: TestLanguage;
  messages: string[];
  expected_behavior: string;
  forbidden_phrases: string[];
  required_phrases: string[];
  severity: "info" | "low" | "medium" | "high" | "critical";
  max_turns: number;
  recommended_tester_mode: TesterMode;
  recommended_judge_mode: JudgeMode;
  provenance: DraftProvenance;
  review_notes: string;
}

export interface ScenarioDraftView extends ScenarioDraftFields {
  id: string;
  owner_id: string;
  status: DraftStatus;
  revision: number;
  approved_scenario_id: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  rejected_at: string | null;
}

export interface PackDraftItem {
  scenario_id: string | null;
  scenario_draft_id: string | null;
  enabled: boolean;
}

export interface TestPackDraftView {
  id: string;
  owner_id: string;
  status: DraftStatus;
  revision: number;
  name: string;
  description: string;
  items: PackDraftItem[];
  provenance: DraftProvenance;
  review_notes: string;
  approved_test_pack_id: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  rejected_at: string | null;
}

export interface AuthoringRuntimeConfig {
  enabled: boolean;
  provider: ProviderId;
  base_url: string;
  model: string;
  system_prompt: string;
  temperature: number;
  maximum_scenarios: number;
}

export interface AuthoringRuntimeStatus {
  enabled: boolean;
  configured: boolean;
  provider: string;
  model: string;
  credential_source: "vault" | "memory" | "environment" | "missing";
}

export interface AuthoringRuntimeView {
  config: AuthoringRuntimeConfig;
  status: AuthoringRuntimeStatus;
}

export interface AuthoringGenerationRequest {
  character_card_id: string;
  language: TestLanguage;
  risk_tags: string[];
  known_failures: string[];
  instructions: string;
  scenario_count: number;
  include_test_pack: boolean;
}

export interface AuthoringGenerationResult {
  scenario_drafts: ScenarioDraftView[];
  test_pack_draft: TestPackDraftView | null;
  warnings: string[];
  provider_model: string;
  prompt_hash: string;
  correction_used: boolean;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve the raw response below.
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

export const authoringApi = {
  runtimeStatus: () =>
    request<AuthoringRuntimeStatus>("/api/authoring/runtime/status"),
  getRuntime: () =>
    request<AuthoringRuntimeView>("/api/admin/authoring-runtime"),
  updateRuntime: (config: AuthoringRuntimeConfig) =>
    request<AuthoringRuntimeView>("/api/admin/authoring-runtime", {
      method: "PUT",
      body: JSON.stringify(config)
    }),
  configureCredential: (apiKey: string) =>
    request<AuthoringRuntimeView>("/api/admin/authoring-runtime/credential", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey })
    }),
  clearCredential: () =>
    request<AuthoringRuntimeView>("/api/admin/authoring-runtime/credential", {
      method: "DELETE"
    }),
  generate: (payload: AuthoringGenerationRequest) =>
    request<AuthoringGenerationResult>("/api/authoring/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listScenarioDrafts: () =>
    request<ScenarioDraftView[]>("/api/authoring/scenario-drafts"),
  updateScenarioDraft: (id: string, payload: ScenarioDraftFields) =>
    request<ScenarioDraftView>(`/api/authoring/scenario-drafts/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  approveScenarioDraft: (id: string) =>
    request<{ draft: ScenarioDraftView; scenario: Record<string, unknown> }>(
      `/api/authoring/scenario-drafts/${id}/approve`,
      { method: "POST" }
    ),
  rejectScenarioDraft: (id: string) =>
    request<ScenarioDraftView>(`/api/authoring/scenario-drafts/${id}/reject`, {
      method: "POST"
    }),
  deleteScenarioDraft: (id: string) =>
    request<void>(`/api/authoring/scenario-drafts/${id}`, { method: "DELETE" }),
  listPackDrafts: () =>
    request<TestPackDraftView[]>("/api/authoring/test-pack-drafts"),
  approvePackDraft: (id: string) =>
    request<{ draft: TestPackDraftView; test_pack: Record<string, unknown> }>(
      `/api/authoring/test-pack-drafts/${id}/approve`,
      { method: "POST" }
    ),
  rejectPackDraft: (id: string) =>
    request<TestPackDraftView>(`/api/authoring/test-pack-drafts/${id}/reject`, {
      method: "POST"
    }),
  deletePackDraft: (id: string) =>
    request<void>(`/api/authoring/test-pack-drafts/${id}`, { method: "DELETE" })
};

export function characterLabel(card: CharacterCard): string {
  return `${card.display_name}${card.subtitle ? ` · ${card.subtitle}` : ""}`;
}
