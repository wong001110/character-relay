import { randomUUID } from "node:crypto";

import type { DiscordConnectorEvent } from "./types.js";

export type DiscordConnectorEventInput = Omit<
  DiscordConnectorEvent,
  "id" | "occurred_at"
>;

export type DiscordConnectorEventSink = (
  events: DiscordConnectorEvent[]
) => Promise<void>;

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

  record(event: DiscordConnectorEventInput): void {
    if (this.queue.length >= this.maximumPending) this.queue.shift();
    const occurredAt = new Date().toISOString();
    this.queue.push({
      id: randomUUID(),
      occurred_at: occurredAt,
      ...event
    });
    this.lastRecordedEventAt = occurredAt;
    this.lastRecordedEventType = event.event_type;
    if (this.queue.length >= this.batchSize) void this.flush();
  }

  async flush(): Promise<void> {
    if (this.flushing || !this.queue.length) return;
    this.flushing = true;
    const batch = this.queue.slice(0, this.batchSize);
    try {
      await this.sink(batch);
      this.queue.splice(0, batch.length);
      this.lastFailure = null;
      this.lastSuccessfulFlushAt = new Date().toISOString();
      this.sentEvents += batch.length;
    } catch (error) {
      this.lastFailure = error instanceof Error ? error.message : String(error);
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
