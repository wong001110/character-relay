import type { CoverageDimension } from "./calibrationApi";
import type { ClassificationMetrics } from "./evaluationApi";

export type CoverageStatus = "missing" | "weak" | "covered";
export type ComparisonClassification = "improved" | "regressed" | "mixed" | "unchanged";

export interface AuthoringGapSuggestion {
  dimension: CoverageDimension;
  risk_tags: string[];
  scenario_categories: string[];
  recommended_count: number;
  reason: string;
}

export interface DimensionCoverage {
  dimension: CoverageDimension;
  case_count: number;
  pass_count: number;
  fail_count: number;
  review_count: number;
  languages: Record<string, number>;
  scenario_categories: Record<string, number>;
  status: CoverageStatus;
  semantic_prediction_count: number;
  semantic_average_score: number | null;
}

export interface DatasetCoverageReport {
  dataset_id: string;
  dataset_name: string;
  dataset_version: number;
  total_cases: number;
  evaluation_id: string | null;
  dimensions: DimensionCoverage[];
  missing_dimensions: CoverageDimension[];
  weak_dimensions: CoverageDimension[];
  suggestions: AuthoringGapSuggestion[];
}

export interface RubricDimensionDelta {
  dimension: string;
  baseline_eligible: number;
  candidate_eligible: number;
  baseline_average: number | null;
  candidate_average: number | null;
  delta: number | null;
}

export interface RubricPredictionChange {
  case_id: string;
  expected_verdict: string;
  baseline_verdict: string | null;
  candidate_verdict: string | null;
  baseline_score: number | null;
  candidate_score: number | null;
  classification: ComparisonClassification;
}

export interface RubricComparisonReport {
  dataset_id: string;
  dataset_name: string;
  dataset_version: number;
  baseline_evaluation_id: string;
  candidate_evaluation_id: string;
  baseline_rubric_version: string;
  candidate_rubric_version: string;
  baseline_metrics: ClassificationMetrics;
  candidate_metrics: ClassificationMetrics;
  accuracy_delta: number;
  macro_f1_delta: number;
  false_positive_rate_delta: number;
  false_negative_rate_delta: number;
  classification: ComparisonClassification;
  dimension_deltas: RubricDimensionDelta[];
  prediction_changes: RubricPredictionChange[];
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

export const coverageApi = {
  report: (datasetId: string, evaluationId?: string) => {
    const query = evaluationId
      ? `?evaluation_id=${encodeURIComponent(evaluationId)}`
      : "";
    return request<DatasetCoverageReport>(
      `/api/analytics/datasets/${encodeURIComponent(datasetId)}/coverage${query}`
    );
  },
  compare: (baselineId: string, candidateId: string) =>
    request<RubricComparisonReport>("/api/analytics/rubrics/compare", {
      method: "POST",
      body: JSON.stringify({
        baseline_evaluation_id: baselineId,
        candidate_evaluation_id: candidateId
      })
    })
};
