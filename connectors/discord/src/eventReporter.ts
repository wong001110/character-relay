import { randomUUID } from "node:crypto";

import { formatSafeDiagnosticError } from "./safeDiagnosticError.js";
import type { DiscordConnectorEvent } from "./types.js";

export type DiscordConnectorEventInput = Omit<
  DiscordConnectorEvent,
  "id" | "occurred_at"
>;

export type DiscordConnectorEventSink = (
  events: DiscordConnectorEvent[]
) => Promise<void>;

const CONTENT_BEARING_DETAIL_TOKENS = new Set([
  "answer",
  "body",
  "completion",
  "text",
  "content",
  "raw",
  "payload",
  "prompt",
  "response",
  "outgoingtext",
  "planningtext",
  "error",
  "lasterror",
  "errormessage",
  "detail",
  "description",
  "input",
  "message",
  "messages",
  "output",
  "preview",
  "query",
  "request",
  "transcript"
]);

const SAFE_STRUCTURED_STRING_SUFFIXES = [
  "_code",
  "_id",
  "_kind",
  "_mode",
  "_reason",
  "_source",
  "_status",
  "_type"
];

function normalizedDetailKey(key: string): string {
  return key
    .replaceAll(/([a-z0-9])([A-Z])/gu, "$1_$2")
    .toLowerCase()
    .replaceAll(/[-\s]+/gu, "_");
}

function isContentBearingDetail(key: string, value: unknown): boolean {
  if (
    typeof value !== "string" &&
    !Array.isArray(value) &&
    (value === null || typeof value !== "object")
  ) {
    return false;
  }
  const normalized = normalizedDetailKey(key);
  const tokens = normalized.split("_");
  const contentBearing = tokens.some((token) => CONTENT_BEARING_DETAIL_TOKENS.has(token));
  const structuredString = SAFE_STRUCTURED_STRING_SUFFIXES.some((suffix) =>
    normalized.endsWith(suffix)
  );
  return contentBearing && !structuredString;
}

function sanitizeDetailValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeDetailValue);
  if (value === null || typeof value !== "object") return value;

  const sanitized: Record<string, unknown> = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    if (isContentBearingDetail(key, nestedValue)) continue;
    sanitized[key] = sanitizeDetailValue(nestedValue);
  }
  return sanitized;
}

function sanitizeDetails(details: Record<string, unknown>): Record<string, unknown> {
  return sanitizeDetailValue(details) as Record<string, unknown>;
}

export class DiscordEventReporter {
  private readonly queue: DiscordConnectorEvent[] = [];
  private timer: NodeJS.Timeout | undefined;
  private flushing = false;
  private lastFailure: string | null = null;
  private lastSuccessfulFlushAt: string | null = null;
  private lastRecordedEventAt: string | null = null;
  private lastRecordedEventType: string | null = null;
  private sentEvents = 0;

  constructor(
    private readonly sink: DiscordConnectorEventSink,
    private readonly flushIntervalMs = 1_500,
    private readonly batchSize = 50,
    private readonly maximumPending = 1_000
  ) {}

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      void this.flush();
    }, this.flushIntervalMs);
  }

  private enqueue(event: DiscordConnectorEventInput): void {
    if (this.queue.length >= this.maximumPending) this.queue.shift();
    const occurredAt = new Date().toISOString();
    this.queue.push({
      id: randomUUID(),
      occurred_at: occurredAt,
      ...event,
      details: sanitizeDetails(event.details)
    });
    this.lastRecordedEventAt = occurredAt;
    this.lastRecordedEventType = event.event_type;
  }

  record(event: DiscordConnectorEventInput): void {
    this.enqueue(event);
    if (this.queue.length >= this.batchSize) void this.flush();
  }

  async flush(): Promise<void> {
    if (this.flushing) return;
    if (!this.queue.length) return;
    this.flushing = true;
    const batch = this.queue.slice(0, this.batchSize);
    try {
      await this.sink(batch);
      this.queue.splice(0, batch.length);
      this.lastFailure = null;
      this.lastSuccessfulFlushAt = new Date().toISOString();
      this.sentEvents += batch.length;
    } catch (error) {
      this.lastFailure = formatSafeDiagnosticError(error);
    } finally {
      this.flushing = false;
    }
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    await this.flush();
  }

  get pendingCount(): number {
    return this.queue.length;
  }

  get lastError(): string | null {
    return this.lastFailure;
  }

  get lastSuccessAt(): string | null {
    return this.lastSuccessfulFlushAt;
  }

  get lastRecordedAt(): string | null {
    return this.lastRecordedEventAt;
  }

  get lastRecordedType(): string | null {
    return this.lastRecordedEventType;
  }

  get sentCount(): number {
    return this.sentEvents;
  }
}
