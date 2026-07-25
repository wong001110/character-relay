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
  waitForTrial: async (id: string): Promise<TrialRun> => {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const run = await request<TrialRun>(`/api/trials/${id}`);
      if (!["pending", "running"].includes(run.status)) return run;
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error("Trial did not finish within the observation window.");
  }
};
