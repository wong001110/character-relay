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
  visibleImageAttachmentCount: number;
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
  onRejected?: (reason: TurnIngressRejectReason) => void;
}

type RuntimeEnqueue = (scopeKey: string, task: () => Promise<void>) => boolean;
type IngressErrorHandler = (error: unknown, scopeKey: string) => void;

export interface TurnIngressLimits {
  maxPending: number;
  maxPendingPerScope: number;
  maxPreflightAgeMs: number;
}

export type TurnIngressRejectReason = "busy" | "expired";

interface CollectedExecution<T> {
  value: T;
  execute: TurnIngressSubmission<T>["execute"];
  onRejected?: TurnIngressSubmission<T>["onRejected"];
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
  const imageOnlyAttachments =
    input.attachmentCount > 0 &&
    input.visibleImageAttachmentCount === input.attachmentCount;
  if (
    input.customEmojiCount > 0 ||
    input.stickerCount > 0 ||
    input.embedCount > 0 ||
    (input.attachmentCount > 0 && !imageOnlyAttachments)
  ) {
    return { collect: false, reason: "rich_content" };
  }
  if (input.hasUrl) return { collect: false, reason: "url_content" };
  if (!input.hasReadableText && !imageOnlyAttachments) {
    return { collect: false, reason: "empty_text" };
  }
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
  private readonly preflightPendingByScope = new Map<string, number>();
  private readonly collectedPendingByScope = new Map<string, number>();
  private preflightPending = 0;
  private collectedPending = 0;
  private readonly collector: TurnCollector<CollectedExecution<T>>;
  private closed = false;

  constructor(
    collectorConfig: Partial<TurnCollectorConfig>,
    private readonly enqueueRuntime: RuntimeEnqueue,
    private readonly onError?: IngressErrorHandler,
    private readonly limits: TurnIngressLimits = {
      maxPending: Number.MAX_SAFE_INTEGER,
      maxPendingPerScope: Number.MAX_SAFE_INTEGER,
      maxPreflightAgeMs: Number.MAX_SAFE_INTEGER
    },
    private readonly onRejected?: (scopeKey: string, reason: TurnIngressRejectReason) => void
  ) {
    this.collector = new TurnCollector<CollectedExecution<T>>(
      collectorConfig,
      async (burst) => {
        const last = burst.items.at(-1);
        if (!last) {
          this.releaseCollected(burst.scopeKey, burst.items.length);
          return;
        }
        const projected: ConversationBurst<T> = {
          ...burst,
          items: burst.items.map((item) => item.value)
        };
        if (
          !this.enqueueRuntime(burst.scopeKey, async () => {
            this.releaseCollected(burst.scopeKey, burst.items.length);
            await last.execute(projected);
          })
        ) {
          this.releaseCollected(burst.scopeKey, burst.items.length);
          last.onRejected?.("busy");
          this.onRejected?.(burst.scopeKey, "busy");
        }
      }
    );
  }

  get enabled(): boolean {
    return this.collector.enabled;
  }

  get currentConfig(): TurnCollectorConfig {
    return this.collector.currentConfig;
  }

  reconfigure(config: Partial<TurnCollectorConfig>): TurnCollectorConfig {
    return this.collector.reconfigure(config);
  }

  get pendingBurstScopeCount(): number {
    return this.collector.pendingScopeCount;
  }

  get pendingPreflightScopeCount(): number {
    return this.preflightQueues.size;
  }

  submit(scopeKey: string, submission: TurnIngressSubmission<T>): boolean {
    if (this.closed) return false;
    if (
      this.preflightPending + this.collectedPending >= this.limits.maxPending ||
      (this.preflightPendingByScope.get(scopeKey) ?? 0) +
        (this.collectedPendingByScope.get(scopeKey) ?? 0) >=
        this.limits.maxPendingPerScope
    ) {
      submission.onRejected?.("busy");
      this.onRejected?.(scopeKey, "busy");
      return false;
    }
    this.preflightPending += 1;
    this.preflightPendingByScope.set(
      scopeKey,
      (this.preflightPendingByScope.get(scopeKey) ?? 0) + 1
    );
    const receivedAt = submission.receivedAt ?? Date.now();
    const executeIfFresh = async (burst: ConversationBurst<T> | null): Promise<void> => {
      // A preflight or collector delay can consume the remaining budget after the
      // initial admission check.  Revalidate immediately before Runtime/API work.
      if (Date.now() - receivedAt > this.limits.maxPreflightAgeMs) {
        submission.onRejected?.("expired");
        this.onRejected?.(scopeKey, "expired");
        return;
      }
      await submission.execute(burst);
    };
    this.enqueuePreflight(scopeKey, async () => {
      if (Date.now() - receivedAt > this.limits.maxPreflightAgeMs) {
        submission.onRejected?.("expired");
        this.onRejected?.(scopeKey, "expired");
        return;
      }
      if (!submission.collect) {
        await this.collector.flush(scopeKey, "explicit_flush");
        if (!this.enqueueRuntime(scopeKey, () => executeIfFresh(null))) {
          submission.onRejected?.("busy");
          this.onRejected?.(scopeKey, "busy");
        }
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
        if (!this.enqueueRuntime(scopeKey, () => executeIfFresh(null))) {
          submission.onRejected?.("busy");
          this.onRejected?.(scopeKey, "busy");
        }
        return;
      }

      this.addCollected(scopeKey);
      this.collector.add(scopeKey, {
        id: submission.id,
        value: {
          value: submission.value,
          execute: executeIfFresh,
          onRejected: submission.onRejected
        },
        characters: submission.characters,
        receivedAt
      });
    });
    return true;
  }

  async shutdown(flushPending = true): Promise<void> {
    this.closed = true;
    const pending = [...this.preflightQueues.values()];
    await Promise.all(pending.map((task) => task.catch(() => undefined)));
    await this.collector.shutdown(flushPending);
    if (!flushPending) {
      this.collectedPending = 0;
      this.collectedPendingByScope.clear();
    }
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
        this.preflightPending = Math.max(0, this.preflightPending - 1);
        const pending = (this.preflightPendingByScope.get(scopeKey) ?? 1) - 1;
        if (pending > 0) this.preflightPendingByScope.set(scopeKey, pending);
        else this.preflightPendingByScope.delete(scopeKey);
        if (this.preflightQueues.get(scopeKey) === next) {
          this.preflightQueues.delete(scopeKey);
        }
      });
    this.preflightQueues.set(scopeKey, next);
  }

  private addCollected(scopeKey: string): void {
    this.collectedPending += 1;
    this.collectedPendingByScope.set(
      scopeKey,
      (this.collectedPendingByScope.get(scopeKey) ?? 0) + 1
    );
  }

  private releaseCollected(scopeKey: string, count: number): void {
    const released = Math.max(0, Math.min(count, this.collectedPendingByScope.get(scopeKey) ?? 0));
    this.collectedPending = Math.max(0, this.collectedPending - released);
    const remaining = (this.collectedPendingByScope.get(scopeKey) ?? 0) - released;
    if (remaining > 0) this.collectedPendingByScope.set(scopeKey, remaining);
    else this.collectedPendingByScope.delete(scopeKey);
  }
}
