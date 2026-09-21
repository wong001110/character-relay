/** Delivery receipts are authority; an exception is not proof that nothing was sent. */
export type DeliveryState = "unsent" | "partial" | "uncertain";

export class DiscordDeliveryError extends Error {
  readonly sentMessageIds: readonly string[];

  constructor(
    readonly state: DeliveryState,
    messageIds: readonly string[] = [],
    readonly status?: number
  ) {
    super(`Discord delivery ${state}${status === undefined ? "." : ` (HTTP ${status}).`}`);
    this.name = "DiscordDeliveryError";
    this.sentMessageIds = Object.freeze([...new Set(messageIds)]);
  }
}

export function deliveryFailure(
  error: unknown,
  confirmedIds: readonly string[] = []
): DiscordDeliveryError {
  // Only a typed error knows whether the message-creation request was attempted.
  // Generic failures, malformed acknowledgements and transport timeouts are uncertain.
  const known = error instanceof DiscordDeliveryError ? error : undefined;
  const ids = [...confirmedIds, ...(known?.sentMessageIds ?? [])];
  const state = known?.state === "unsent" && ids.length ? "partial" : known?.state ?? "uncertain";
  return new DiscordDeliveryError(state, ids, known?.status);
}

export function canFallbackDelivery(error: unknown): boolean {
  return error instanceof DiscordDeliveryError && error.state === "unsent" &&
    error.sentMessageIds.length === 0 && error.status !== 429;
}

export async function deliverWithFallback(
  primary: () => Promise<string[]>,
  fallback: () => Promise<string[]>
): Promise<string[]> {
  try {
    return await primary();
  } catch (error) {
    if (!canFallbackDelivery(error)) throw error;
    return fallback();
  }
}

export async function readDeliveryReceipt(response: Response): Promise<string> {
  if (!response.ok) {
    // Rate-limited attempts are known rejected, but must not bypass that limit via another identity.
    const rejected = response.status >= 400 && response.status < 500;
    throw new DiscordDeliveryError(rejected ? "unsent" : "uncertain", [], response.status);
  }
  const value: unknown = await response.json();
  if (!value || typeof value !== "object" || !("id" in value) ||
      typeof value.id !== "string" || !value.id.trim() || value.id.length > 200) {
    throw new DiscordDeliveryError("uncertain");
  }
  return value.id;
}

export async function sendChunks(
  chunks: readonly string[],
  send: (chunk: string, index: number) => Promise<string>
): Promise<string[]> {
  const ids: string[] = [];
  try {
    for (const [index, chunk] of chunks.filter(Boolean).entries()) {
      const id = await send(chunk, index);
      if (!id) throw new DiscordDeliveryError("uncertain");
      ids.push(id);
    }
    return ids;
  } catch (error) {
    throw deliveryFailure(error, ids);
  }
}
