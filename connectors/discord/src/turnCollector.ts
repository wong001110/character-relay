export type TurnCollectorFlushReason =
  | "quiet_window"
  | "max_wait"
  | "max_messages"
  | "max_characters"
  | "explicit_flush"
  | "shutdown";

export interface TurnCollectorConfig {
  enabled: boolean;
  quietWindowMs: number;
  maxWaitMs: number;
  maxMessages: number;
  maxCharacters: number;
}

export interface TurnCollectorInput<T> {
  id: string;
  value: T;
  characters: number;
  receivedAt?: number;
}

export interface ConversationBurst<T> {
  scopeKey: string;
  items: T[];
  itemIds: string[];
  totalCharacters: number;
  openedAt: number;
  flushedAt: number;
  reason: TurnCollectorFlushReason;
}

type FlushHandler<T> = (burst: ConversationBurst<T>) => void | Promise<void>;

interface PendingBurst<T> {
  items: TurnCollectorInput<T>[];
  openedAt: number;
  totalCharacters: number;
  quietTimer: ReturnType<typeof setTimeout> | null;
  maxTimer: ReturnType<typeof setTimeout> | null;
}

const DEFAULTS: TurnCollectorConfig = {
  enabled: true,
  quietWindowMs: 1_500,
  maxWaitMs: 4_000,
  maxMessages: 5,
  maxCharacters: 1_500
};

function boundedInteger(value: number, fallback: number, minimum: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(minimum, Math.floor(value));
}

export class TurnCollector<T> {
  private readonly config: TurnCollectorConfig;
  private readonly pending = new Map<string, PendingBurst<T>>();

  constructor(
    config: Partial<TurnCollectorConfig>,
    private readonly onFlush: FlushHandler<T>
  ) {
    const quietWindowMs = boundedInteger(
      config.quietWindowMs ?? DEFAULTS.quietWindowMs,
      DEFAULTS.quietWindowMs,
      1
    );
    const maxWaitMs = Math.max(
      quietWindowMs,
      boundedInteger(
        config.maxWaitMs ?? DEFAULTS.maxWaitMs,
        DEFAULTS.maxWaitMs,
        quietWindowMs
      )
    );
    this.config = {
      enabled: config.enabled ?? DEFAULTS.enabled,
      quietWindowMs,
      maxWaitMs,
      maxMessages: boundedInteger(
        config.maxMessages ?? DEFAULTS.maxMessages,
        DEFAULTS.maxMessages,
        1
      ),
      maxCharacters: boundedInteger(
        config.maxCharacters ?? DEFAULTS.maxCharacters,
        DEFAULTS.maxCharacters,
        1
      )
    };
  }

  get enabled(): boolean {
    return this.config.enabled;
  }

  get pendingScopeCount(): number {
    return this.pending.size;
  }

  add(scopeKey: string, input: TurnCollectorInput<T>): void {
    if (!this.config.enabled) {
      void this.onFlush({
        scopeKey,
        items: [input.value],
        itemIds: [input.id],
        totalCharacters: Math.max(0, input.characters),
        openedAt: input.receivedAt ?? Date.now(),
        flushedAt: Date.now(),
        reason: "explicit_flush"
      });
      return;
    }

    const now = input.receivedAt ?? Date.now();
    let burst = this.pending.get(scopeKey);
    if (!burst) {
      burst = {
        items: [],
        openedAt: now,
        totalCharacters: 0,
        quietTimer: null,
        maxTimer: null
      };
      this.pending.set(scopeKey, burst);
      burst.maxTimer = setTimeout(() => {
        void this.flush(scopeKey, "max_wait");
      }, this.config.maxWaitMs);
    }

    if (burst.items.some((item) => item.id === input.id)) return;

    burst.items.push(input);
    burst.totalCharacters += Math.max(0, input.characters);

    if (burst.quietTimer) clearTimeout(burst.quietTimer);
    burst.quietTimer = setTimeout(() => {
      void this.flush(scopeKey, "quiet_window");
    }, this.config.quietWindowMs);

    if (burst.items.length >= this.config.maxMessages) {
      void this.flush(scopeKey, "max_messages");
      return;
    }
    if (burst.totalCharacters >= this.config.maxCharacters) {
      void this.flush(scopeKey, "max_characters");
    }
  }

  async flush(
    scopeKey: string,
    reason: TurnCollectorFlushReason = "explicit_flush"
  ): Promise<boolean> {
    const burst = this.pending.get(scopeKey);
    if (!burst || !burst.items.length) return false;
    this.pending.delete(scopeKey);
    if (burst.quietTimer) clearTimeout(burst.quietTimer);
    if (burst.maxTimer) clearTimeout(burst.maxTimer);

    await this.onFlush({
      scopeKey,
      items: burst.items.map((item) => item.value),
      itemIds: burst.items.map((item) => item.id),
      totalCharacters: burst.totalCharacters,
      openedAt: burst.openedAt,
      flushedAt: Date.now(),
      reason
    });
    return true;
  }

  async shutdown(flushPending = false): Promise<void> {
    const scopes = [...this.pending.keys()];
    if (flushPending) {
      for (const scopeKey of scopes) {
        await this.flush(scopeKey, "shutdown");
      }
      return;
    }
    for (const scopeKey of scopes) {
      const burst = this.pending.get(scopeKey);
      if (burst?.quietTimer) clearTimeout(burst.quietTimer);
      if (burst?.maxTimer) clearTimeout(burst.maxTimer);
      this.pending.delete(scopeKey);
    }
  }
}
