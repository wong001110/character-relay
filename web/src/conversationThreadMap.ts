import type {
  ConversationSegmentObservation,
  ConversationThreadObservation
} from "./conversationStructureApi";
import { pageItems } from "./conversationPagination";

export const THREAD_MAP_PAGE_SIZE = 8;
export const THREAD_SEGMENT_PAGE_SIZE = 6;

export interface ConversationThreadMapItem {
  thread: ConversationThreadObservation;
  segments: ConversationSegmentObservation[];
}

export interface ConversationThreadMap {
  threads: ConversationThreadMapItem[];
  unresolvedSegments: ConversationSegmentObservation[];
}

function compact(value: string): string {
  return value
    .replace(/https?:\/\/\S+/giu, "link")
    .replace(/\s+/gu, " ")
    .trim();
}

export function threadDisplayTitle(thread: ConversationThreadObservation, maximumLength = 84): string {
  const title = compact(thread.canonical_label || thread.anchor_summary || thread.working_summary);
  if (!title) return `Thread ${thread.id.slice(0, 8) || "—"}`;
  return title.length > maximumLength ? `${title.slice(0, Math.max(1, maximumLength - 1)).trimEnd()}…` : title;
}

export function threadDisplaySummary(thread: ConversationThreadObservation, maximumLength = 160): string {
  const summary = compact(thread.working_summary || thread.anchor_summary);
  if (!summary) return "—";
  return summary.length > maximumLength ? `${summary.slice(0, Math.max(1, maximumLength - 1)).trimEnd()}…` : summary;
}

export function segmentDisplaySummary(segment: ConversationSegmentObservation, maximumLength = 220): string {
  const summary = compact(segment.summary);
  if (!summary) return "—";
  return summary.length > maximumLength ? `${summary.slice(0, Math.max(1, maximumLength - 1)).trimEnd()}…` : summary;
}

function lastActiveAt(thread: ConversationThreadObservation): number {
  const timestamp = Date.parse(thread.last_active_at);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function buildConversationThreadMap(
  threads: ConversationThreadObservation[],
  segments: ConversationSegmentObservation[]
): ConversationThreadMap {
  const segmentsByThread = new Map<string, ConversationSegmentObservation[]>();
  const knownThreadIds = new Set(threads.map((thread) => thread.id));
  const unresolvedSegments: ConversationSegmentObservation[] = [];

  for (const segment of segments) {
    if (!segment.thread_id || !knownThreadIds.has(segment.thread_id) || segment.membership_relation === "unresolved") {
      unresolvedSegments.push(segment);
      continue;
    }
    const threadSegments = segmentsByThread.get(segment.thread_id) ?? [];
    threadSegments.push(segment);
    segmentsByThread.set(segment.thread_id, threadSegments);
  }

  return {
    threads: [...threads.map((thread) => ({ thread, segments: segmentsByThread.get(thread.id) ?? [] }))]
      .sort((left, right) => lastActiveAt(right.thread) - lastActiveAt(left.thread)),
    unresolvedSegments
  };
}

export { pageItems };
