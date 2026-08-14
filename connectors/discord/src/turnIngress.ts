import { createHash } from "node:crypto";

import {
  TurnCollector,
  type ConversationBurst,
  type TurnCollectorConfig,
  type TurnCollectorFlushReason
} from "./turnCollector.js";

export type TurnCollectionReason =
  | "collect"
  | "collector_disabled"
  | "smart_participation_disabled"
  | "recovery"
  | "bot_mention"
  | "reply_reference"
  | "explicit_audience"
  | "rich_content"
  | "url_content"
  | "empty_text"
  | "no_smart_candidates";

export interface TurnCollectionPolicyInput {
  collectorEnabled: boolean;
  smartParticipationEnabled: boolean;
  recovery: boolean;
  mentionedBot: boolean;
  hasReplyReference: boolean;
  explicitAudience: boolean;
  hasReadableText: boolean;
  customEmojiCount: number;
  stickerCount: number;
  attachmentCount: number;
  embedCount: number;
  hasUrl: boolean;
  smartCandidateCount: number;
}

export interface TurnCollectionDecision {
  collect: boolean;
  reason: TurnCollectionReason;
}

export interface ConversationBurstTextPart {
  text: string;
}

export interface ConversationBurstTelemetry {
  burstId: string;
  flushReason: TurnCollectorFlushReason;
  messageCount: number;
  authorCount: number;
  totalCharacters: number;
  openedAt: number;
  flushedAt: number;
  collectionLatencyMs: number;
  collapsedMessageCount: number;
  sourceMessageIds: string[];
}

export interface TurnIngressSubmission<T> {
  id: string;
  value: T;
  characters: number;
  receivedAt?: number;
  collect: boolean;
  prepareCollection?: () => Promise<boolean>;
  execute: (burst: ConversationBurst<T> | null) => Promise<void>;
}

type RuntimeEnqueue = (scopeKey: string, task: () => Promise<void>) => void;
type IngressErrorHandler = (error: unknown, scopeKey: string) => void;

interface CollectedExecution<T> {
  value: T;
  execute: TurnIngressSubmission<T>["execute"];
}

export function decideTurnCollection(
  input: TurnCollectionPolicyInput
): TurnCollectionDecision {
  if (!input.collectorEnabled) return { collect: false, reason: "collector_disabled" };
  if (!input.smartParticipationEnabled) {
    return { collect: false, reason: "smart_participation_disabled" };
  }
  if (input.recovery) return { collect: false, reason: "recovery" };
  if (input.mentionedBot) return { collect: false, reason: "bot_mention" };
  if (input.hasReplyReference) return { collect: false, reason: "reply_reference" };
  if (input.explicitAudience) return { collect: false, reason: "explicit_audience" };
  if (
    input.customEmojiCount > 0 ||
    input.stickerCount > 0 ||
    input.attachmentCount > 0 ||
    input.embedCount > 0
  ) {
    return { collect: false, reason: "rich_content" };
  }
  if (input.hasUrl) return { collect: false, reason: "url_content" };
  if (!input.hasReadableText) return { collect: false, reason: "empty_text" };
  if (input.smartCandidateCount <= 0) {
    return { collect: false, reason: "no_smart_candidates" };
  }
  return { collect: true, reason: "collect" };
}

export function buildConversationBurstId(itemIds: readonly string[]): string {
  const source = [...new Set(itemIds.map((item) => item.trim()).filter(Boolean))].join("|");
  if (!source) return "";
  return createHash("sha256").update(source).digest("hex").slice(0, 40);
}

export function buildConversationBurstText(
  parts: readonly ConversationBurstTextPart[],
  maximumCharacters = 4_000
): string {
  const maximum = Math.max(1, Math.floor(maximumCharacters));
  const text = parts
    .map((item) => item.text.replace(/\s+/gu, " ").trim())
    .filter(Boolean)
    .join("\n");
  return text.length <= maximum ? text : text.slice(text.length - maximum);
}

export function summarizeConversationBurst<T>(
  burst: ConversationBurst<T>,
  authorIds: readonly string[]
): ConversationBurstTelemetry {
  const sourceMessageIds = [...burst.itemIds];
  const authors = new Set(authorIds.map((item) => item.trim()).filter(Boolean));
  return {
    burstId: buildConversationBurstId(sourceMessageIds),
    flushReason: burst.reason,
    messageCount: sourceMessageIds.length,
    authorCount: authors.size,
    totalCharacters: Math.max(0, burst.totalCharacters),
    openedAt: burst.openedAt,
    flushedAt: burst.flushedAt,
    collectionLatencyMs: Math.max(0, burst.flushedAt - burst.openedAt),
    collapsedMessageCount: Math.max(0, sourceMessageIds.length - 1),
    sourceMessageIds
  };
}

export class TurnIngressCoordinator<T> {
  private readonly preflightQueues = new Map<string, Promise<void>>();
  private readonly collector: TurnCollector<CollectedExecution<T>>;
  private closed = false;

  constructor(
    collectorConfig: Partial<TurnCollectorConfig>,
    private readonly enqueueRuntime: RuntimeEnqueue,
    private readonly onError?: IngressErrorHandler
  ) {
    this.collector = new TurnCollector<CollectedExecution<T>>(
      collectorConfig,
      async (burst) => {
        const last = burst.items.at(-1);
        if (!last) return;
        const projected: ConversationBurst<T> = {
          ...burst,
          items: burst.items.map((item) => item.value)
        };
        this.enqueueRuntime(burst.scopeKey, () => last.execute(projected));
      }
    );
  }

  get enabled(): boolean {
    return this.collector.enabled;
  }

  get pendingBurstScopeCount(): number {
    return this.collector.pendingScopeCount;
  }

  get pendingPreflightScopeCount(): number {
    return this.preflightQueues.size;
  }

  submit(scopeKey: string, submission: TurnIngressSubmission<T>): void {
    if (this.closed) return;
    this.enqueuePreflight(scopeKey, async () => {
      if (!submission.collect) {
        await this.collector.flush(scopeKey, "explicit_flush");
        this.enqueueRuntime(scopeKey, () => submission.execute(null));
        return;
      }

      let collect = true;
      if (submission.prepareCollection) {
        try {
          collect = await submission.prepareCollection();
        } catch (error) {
          collect = false;
          this.onError?.(error, scopeKey);
        }
      }
      if (!collect) {
        await this.collector.flush(scopeKey, "explicit_flush");
        this.enqueueRuntime(scopeKey, () => submission.execute(null));
        return;
      }

      this.collector.add(scopeKey, {
        id: submission.id,
        value: { value: submission.value, execute: submission.execute },
        characters: submission.characters,
        ...(submission.receivedAt !== undefined ? { receivedAt: submission.receivedAt } : {})
      });
    });
  }

  async shutdown(flushPending = true): Promise<void> {
    this.closed = true;
    const pending = [...this.preflightQueues.values()];
    await Promise.all(pending.map((task) => task.catch(() => undefined)));
    await this.collector.shutdown(flushPending);
  }

  private enqueuePreflight(scopeKey: string, task: () => Promise<void>): void {
    const previous = this.preflightQueues.get(scopeKey) ?? Promise.resolve();
    let next: Promise<void>;
    next = previous
      .catch(() => undefined)
      .then(task)
      .catch((error: unknown) => {
        this.onError?.(error, scopeKey);
      })
      .finally(() => {
        if (this.preflightQueues.get(scopeKey) === next) {
          this.preflightQueues.delete(scopeKey);
        }
      });
    this.preflightQueues.set(scopeKey, next);
  }
}
