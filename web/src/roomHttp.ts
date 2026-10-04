/** Same-origin session transport. Never accepts Discord credentials or renders server HTML. */
export class RoomRequestError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}
export async function roomRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const body: unknown = await response.json(); if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") detail = body.detail; } catch { /* No untrusted HTML or error body rendered. */ }
    throw new RoomRequestError(response.status, detail);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
