export type EvaluationMode = "rules" | "semantic" | "hybrid";
export type EvaluationVerdict = "PASS" | "FAIL" | "REVIEW";

export interface ClassificationMetrics {
  eligible: number;
  correct: number;
  accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  false_positive_count: number;
  false_positive_rate: number;
  false_negative_count: number;
  false_negative_rate: number;
  confusion: Record<string, Record<string, number>>;
  per_class: Record<string, Record<string, number>>;
}

export interface JudgeEvaluationMetrics {
  by_mode: Record<EvaluationMode, ClassificationMetrics>;
  rules_semantic_agreement: {
    eligible: number;
    agreements: number;
    disagreements: number;
    agreement_rate: number;
  };
  by_failure_type: Record<string, Record<EvaluationMode, ClassificationMetrics>>;
  by_language: Record<string, Record<EvaluationMode, ClassificationMetrics>>;
  by_scenario_category: Record<string, Record<EvaluationMode, ClassificationMetrics>>;
  by_character: Record<string, Record<EvaluationMode, ClassificationMetrics>>;
}

export interface JudgePredictionView {
  id: string;
  evaluation_id: string;
  case_id: string;
  mode: EvaluationMode;
  expected_verdict: EvaluationVerdict;
  predicted_verdict: EvaluationVerdict | null;
  score: number | null;
  confidence: number | null;
  failure_types: string[];
  dimensions: Record<string, number>;
  evidence: Array<Record<string, unknown>>;
  contract_source: "run_snapshot" | "current_character" | "generic";
  error: string | null;
  created_at: string;
}

export interface JudgeEvaluationView {
  id: string;
  owner_id: string;
  dataset_id: string;
  dataset_version: number;
  dataset_name: string;
  modes: EvaluationMode[];
  judge_config: Record<string, unknown>;
  metrics: JudgeEvaluationMetrics;
  status: "completed" | "partial" | "failed";
  predictions: JudgePredictionView[];
  created_at: string;
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

export const evaluationApi = {
  list: () => request<JudgeEvaluationView[]>("/api/evaluations"),
  get: (id: string) => request<JudgeEvaluationView>(`/api/evaluations/${id}`),
  run: (datasetId: string, modes: EvaluationMode[]) =>
    request<JudgeEvaluationView>("/api/evaluations", {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId, modes })
    })
};
