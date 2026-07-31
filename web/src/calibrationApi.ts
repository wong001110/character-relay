export type CalibrationStatus = "draft" | "approved" | "archived";
export type CalibrationVerdict = "PASS" | "FAIL" | "REVIEW";
export type CoverageDimension =
  | "identity"
  | "memory"
  | "instruction_resistance"
  | "capability_honesty"
  | "persona"
  | "language";

export interface CalibrationCaseFields {
  scenario_id: string | null;
  character_card_id: string | null;
  scenario_name: string;
  scenario_category: string;
  language: "en" | "zh-CN";
  turn_index: number | null;
  tester_message: string;
  subject_response: string;
  expected_verdict: CalibrationVerdict;
  failure_type: string;
  evidence_excerpt: string;
  coverage_dimensions: CoverageDimension[];
  notes: string;
}

export interface CalibrationCaseView extends CalibrationCaseFields {
  id: string;
  dataset_id: string;
  owner_id: string;
  position: number;
  source: "manual" | "run";
  run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalibrationDatasetView {
  id: string;
  owner_id: string;
  lineage_id: string;
  parent_dataset_id: string | null;
  name: string;
  description: string;
  version: number;
  status: CalibrationStatus;
  cases: CalibrationCaseView[];
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  archived_at: string | null;
}

export interface CalibrationRunImport {
  run_id: string;
  scenario_id: string;
  turn_index: number;
  expected_verdict: CalibrationVerdict;
  failure_type: string;
  evidence_excerpt: string;
  coverage_dimensions: CoverageDimension[];
  notes: string;
}

export interface CalibrationArchive {
  schema_version: "1";
  exported_at: string;
  owner_id: string;
  datasets: CalibrationDatasetView[];
}

async function detail(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const value = JSON.parse(raw) as { detail?: unknown };
    if (typeof value.detail === "string") return value.detail;
  } catch {
    // Preserve raw response.
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
  if (!response.ok) throw new Error(await detail(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const calibrationApi = {
  list: () => request<CalibrationDatasetView[]>("/api/calibration/datasets"),
  create: (name: string, description: string) =>
    request<CalibrationDatasetView>("/api/calibration/datasets", {
      method: "POST",
      body: JSON.stringify({ name, description })
    }),
  update: (id: string, name: string, description: string) =>
    request<CalibrationDatasetView>(`/api/calibration/datasets/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name, description })
    }),
  approve: (id: string) =>
    request<CalibrationDatasetView>(`/api/calibration/datasets/${id}/approve`, {
      method: "POST"
    }),
  archive: (id: string) =>
    request<CalibrationDatasetView>(`/api/calibration/datasets/${id}/archive`, {
      method: "POST"
    }),
  nextVersion: (id: string) =>
    request<CalibrationDatasetView>(`/api/calibration/datasets/${id}/new-version`, {
      method: "POST"
    }),
  remove: (id: string) =>
    request<void>(`/api/calibration/datasets/${id}`, { method: "DELETE" }),
  createCase: (datasetId: string, payload: CalibrationCaseFields) =>
    request<CalibrationCaseView>(`/api/calibration/datasets/${datasetId}/cases`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  importRun: (datasetId: string, payload: CalibrationRunImport) =>
    request<CalibrationCaseView>(
      `/api/calibration/datasets/${datasetId}/cases/import-run`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  updateCase: (id: string, payload: CalibrationCaseFields) =>
    request<CalibrationCaseView>(`/api/calibration/cases/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  removeCase: (id: string) =>
    request<void>(`/api/calibration/cases/${id}`, { method: "DELETE" }),
  exportArchive: () => request<CalibrationArchive>("/api/calibration/archive"),
  importArchive: (archive: CalibrationArchive, mode: "merge" | "replace") =>
    request<{ imported: Record<string, number>; skipped: Record<string, number> }>(
      "/api/calibration/archive/import",
      { method: "POST", body: JSON.stringify({ archive, mode }) }
    )
};
