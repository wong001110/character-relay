import type { TestLanguage } from "./api";
import type { ScenarioDraftView, TestPackDraftView } from "./authoringApi";
import type { ScenarioView, TestPackView } from "./workspaceApi";

export interface EvaluationTemplateView {
  id: string;
  name: string;
  description: string;
  risk_tags: string[];
  scenario_count: number;
  supported_languages: TestLanguage[];
}

export interface TemplateInstantiationResult {
  scenario_drafts: ScenarioDraftView[];
  test_pack_draft: TestPackDraftView;
}

export interface ShareScenarioAsset {
  key: string;
  name: string;
  category: string;
  description: string;
  language: string;
  messages: string[];
  expected_behavior: string;
  forbidden_phrases: string[];
  required_phrases: string[];
  severity: string;
  max_turns: number;
  recommended_tester_mode: string;
  recommended_judge_mode: string;
}

export interface EvaluationShareBundle {
  schema_version: "1";
  title: string;
  description: string;
  exported_at: string;
  scenarios: ShareScenarioAsset[];
  test_packs: Array<{
    key: string;
    name: string;
    description: string;
    items: Array<{ scenario_key: string; enabled: boolean }>;
  }>;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }
  });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") throw new Error(parsed.detail);
    } catch (reason) {
      if (reason instanceof Error) throw reason;
    }
    throw new Error(raw || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const templateApi = {
  list: () => request<EvaluationTemplateView[]>("/api/templates"),
  instantiate: (templateId: string, language: TestLanguage, characterCardId: string | null) =>
    request<TemplateInstantiationResult>(`/api/templates/${encodeURIComponent(templateId)}/instantiate`, {
      method: "POST",
      body: JSON.stringify({ language, character_card_id: characterCardId })
    }),
  exportBundle: (
    title: string,
    description: string,
    scenarios: ScenarioView[],
    packs: TestPackView[]
  ) => request<EvaluationShareBundle>("/api/share-bundles/export", {
    method: "POST",
    body: JSON.stringify({
      title,
      description,
      scenario_ids: scenarios.map((item) => item.id),
      test_pack_ids: packs.map((item) => item.id)
    })
  }),
  importBundle: (bundle: EvaluationShareBundle) =>
    request<{ scenario_drafts: ScenarioDraftView[]; test_pack_drafts: TestPackDraftView[] }>(
      "/api/share-bundles/import",
      { method: "POST", body: JSON.stringify({ bundle }) }
    )
};
