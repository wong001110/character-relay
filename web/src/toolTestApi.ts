export type ToolTestStatus = "completed" | "failed" | "rejected";

export interface ToolTestDeployment {
  deployment_id: string;
  owner_id: string;
  character_card_id: string;
  character_name: string;
  platform: string;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  timezone: string;
  enabled_tools: string[];
}

export interface ToolTestExecutePayload {
  deployment_id: string;
  tool_id: string;
  arguments: Record<string, unknown>;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  message_id: string;
  initiator_user_id: string;
  trigger_text: string;
  confirm_side_effect: boolean;
}

export interface ToolTestResult {
  deployment_id: string;
  tool_id: string;
  provider_function_name: string;
  side_effect: boolean;
  status: ToolTestStatus;
  duration_ms: number;
  error: string;
  timezone: string;
  result: unknown;
  raw_content: string;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response below.
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
  return response.json() as Promise<T>;
}

export const toolTestApi = {
  listDeployments: () => request<ToolTestDeployment[]>("/api/tools/test/deployments"),
  execute: (payload: ToolTestExecutePayload) =>
    request<ToolTestResult>("/api/tools/test/execute", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
