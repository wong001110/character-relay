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
  config: TurnCollectorConfig;
  quietTimer: ReturnType<typeof setTimeout> | null;
  maxTimer: ReturnType<typeof setTimeout> | null;
}

const DEFAULTS: TurnCollectorConfig = {
  enabled: true,
  quietWindowMs: 3_000,
  maxWaitMs: 10_000,
  maxMessages: 5,
  maxCharacters: 1_500
};

function boundedInteger(value: number, fallback: number, minimum: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(minimum, Math.floor(value));
}

function normalizedConfig(
  config: Partial<TurnCollectorConfig>,
  current: TurnCollectorConfig = DEFAULTS
): TurnCollectorConfig {
  const quietWindowMs = boundedInteger(
    config.quietWindowMs ?? current.quietWindowMs,
    current.quietWindowMs,
    1
  );
  const maxWaitMs = Math.max(
    quietWindowMs,
    boundedInteger(
      config.maxWaitMs ?? current.maxWaitMs,
      current.maxWaitMs,
      quietWindowMs
    )
  );
  return {
    enabled: config.enabled ?? current.enabled,
    quietWindowMs,
    maxWaitMs,
    maxMessages: boundedInteger(
      config.maxMessages ?? current.maxMessages,
      current.maxMessages,
      1
    ),
    maxCharacters: boundedInteger(
      config.maxCharacters ?? current.maxCharacters,
      current.maxCharacters,
      1
    )
  };
}

export class TurnCollector<T> {
  private config: TurnCollectorConfig;
  private readonly pending = new Map<string, PendingBurst<T>>();

  constructor(
    config: Partial<TurnCollectorConfig>,
    private readonly onFlush: FlushHandler<T>
  ) {
    this.config = normalizedConfig(config);
  }

  get enabled(): boolean {
    return this.config.enabled;
  }

  get currentConfig(): TurnCollectorConfig {
    return { ...this.config };
  }

  get pendingScopeCount(): number {
    return this.pending.size;
  }

  reconfigure(config: Partial<TurnCollectorConfig>): TurnCollectorConfig {
    this.config = normalizedConfig(config, this.config);
    return this.currentConfig;
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
      const burstConfig = this.currentConfig;
      burst = {
        items: [],
        openedAt: now,
        totalCharacters: 0,
        config: burstConfig,
        quietTimer: null,
        maxTimer: null
      };
      this.pending.set(scopeKey, burst);
      burst.maxTimer = setTimeout(() => {
        void this.flush(scopeKey, "max_wait");
      }, burstConfig.maxWaitMs);
    }

    if (burst.items.some((item) => item.id === input.id)) return;

    burst.items.push(input);
    burst.totalCharacters += Math.max(0, input.characters);

    if (burst.quietTimer) clearTimeout(burst.quietTimer);
    burst.quietTimer = setTimeout(() => {
      void this.flush(scopeKey, "quiet_window");
    }, burst.config.quietWindowMs);

    if (burst.items.length >= burst.config.maxMessages) {
      void this.flush(scopeKey, "max_messages");
      return;
    }
    if (burst.totalCharacters >= burst.config.maxCharacters) {
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
