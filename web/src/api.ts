export type TestKind =
  | "identity_integrity"
  | "false_memory"
  | "prompt_injection"
  | "long_conversation_drift";

export interface TargetView {
  id: string;
  name: string;
  target_kind: string;
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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listTargets: () => request<TargetView[]>("/api/targets"),
  startTrial: (targetId: string, suite: TestKind[]) =>
    request<TrialRun>("/api/trials", {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, suite })
    }),
  getTrial: (id: string) => request<TrialRun>(`/api/trials/${id}`),
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
  waitForTrial: async (id: string): Promise<TrialRun> => {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const run = await request<TrialRun>(`/api/trials/${id}`);
      if (!["pending", "running"].includes(run.status)) return run;
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error("Trial did not finish within the observation window.");
  }
};
