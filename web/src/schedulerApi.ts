export type ScheduledReminderStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface ScheduledReminder {
  id: string;
  deployment_id: string;
  character_card_id: string;
  character_name: string;
  platform: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  reminder_text: string;
  scheduled_at: string;
  status: ScheduledReminderStatus;
  attempt_count: number;
  delivered_at: string | null;
  last_error: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduledReminderList {
  items: ScheduledReminder[];
}

export interface ScheduledReminderCounts {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface ScheduledReminderPage {
  items: ScheduledReminder[];
  next_cursor: string | null;
  has_more: boolean;
  counts: ScheduledReminderCounts;
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

export const schedulerApi = {
  list: (options: {
    deploymentId?: string;
    status?: ScheduledReminderStatus | "all";
    limit?: number;
    signal?: AbortSignal;
  } = {}) => {
    const query = new URLSearchParams({ limit: String(options.limit ?? 100) });
    if (options.deploymentId?.trim()) {
      query.set("deployment_id", options.deploymentId.trim());
    }
    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    return request<ScheduledReminderList>(
      `/api/scheduler/reminders?${query.toString()}`,
      { signal: options.signal }
    );
  },
  page: (options: {
    deploymentId?: string;
    status?: ScheduledReminderStatus | "all";
    limit?: number;
    cursor?: string | null;
    signal?: AbortSignal;
  } = {}) => {
    const query = new URLSearchParams({ limit: String(options.limit ?? 50) });
    if (options.deploymentId?.trim()) {
      query.set("deployment_id", options.deploymentId.trim());
    }
    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    if (options.cursor) query.set("cursor", options.cursor);
    return request<ScheduledReminderPage>(
      `/api/scheduler/reminders/page?${query.toString()}`,
      { signal: options.signal }
    );
  },
  cancel: (reminderId: string) =>
    request<ScheduledReminder>(
      `/api/scheduler/reminders/${encodeURIComponent(reminderId)}`,
      { method: "DELETE" }
    )
};
