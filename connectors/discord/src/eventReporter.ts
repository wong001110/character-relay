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
    this.queue.push({
      id: randomUUID(),
      occurred_at: new Date().toISOString(),
      ...event
    });
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
}
