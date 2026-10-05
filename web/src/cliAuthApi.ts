/** Official browser approval transport. Browser sessions and CSRF stay in memory. */
export interface CliAccount { user_id: string; display_name: string; email: string }
export interface CliBrowserContext { csrf_token: string; account: CliAccount }
export interface CliAuthorizationReview {
  client_id: string;
  client_name: string;
  account: CliAccount;
  rooms: Array<{ id: string; name: string }>;
  scopes: string[];
  device_expires_at: string;
  access_token_ttl_seconds: number;
}
export interface CliGrant {
  grant_id: string;
  client_id: string;
  client_name: string;
  scopes: string[];
  room_ids: string[];
  approved_at: string;
  expires_at: string;
  revoked_at: string | null;
}

export class CliBrowserRequestError extends Error {
  constructor(public readonly status: number) {
    super(`CLI authorization request failed (${status}).`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/cli-auth/${path}`, {
    ...init,
    credentials: "same-origin",
    redirect: "error",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...init.headers }
  });
  if (!response.ok) throw new CliBrowserRequestError(response.status);
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const cliAuthApi = {
  context: () => request<CliBrowserContext>("browser-context"),
  review: (userCode: string, csrfToken: string) => request<CliAuthorizationReview>(
    "authorizations/review", {
      method: "POST", headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ user_code: userCode })
    }
  ),
  decide: (userCode: string, decision: "approve" | "deny", csrfToken: string) =>
    request<unknown>("authorizations/decision", {
      method: "POST", headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ user_code: userCode, decision })
    }),
  grants: () => request<{ grants: CliGrant[] }>("grants"),
  revoke: (grantId: string, csrfToken: string) => request<void>(
    `grants/${encodeURIComponent(grantId)}`, {
      method: "DELETE", headers: { "X-CSRF-Token": csrfToken }
    }
  )
};

export function cliErrorMessage(reason: unknown, zh: boolean): string {
  if (reason instanceof CliBrowserRequestError) {
    if (reason.status === 404 || reason.status === 503) {
      return zh ? "CLI 授权当前不可用或尚未启用。" : "CLI authorization is unavailable or has not been enabled.";
    }
    if (reason.status === 401) {
      return zh ? "请重新登录后再试。" : "Please sign in again before continuing.";
    }
    if (reason.status === 429) {
      return zh ? "尝试过于频繁，请稍后再试。" : "Too many attempts. Please try again later.";
    }
  }
  return zh ? "请求未能完成。请检查代码、账户与房间权限后重试。" : "The request could not be completed. Check the code, account and room access, then try again.";
}

export function cliScopeLabel(scope: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    "identity:read": ["Read your identity", "读取你的身份"],
    "rooms:read": ["Read the selected room names", "读取所选房间名称"],
    "messages:read": ["Read recent messages in the selected rooms", "读取所选房间的最近消息"]
  };
  return labels[scope]?.[zh ? 1 : 0] ?? scope;
}
