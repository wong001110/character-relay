import type { MessageRelationObservation } from "./conversationStructureApi";

export const RELATION_BOARD_PAGE_SIZE = 12;

export interface RelationParticipants {
  source: string;
  target: string;
}

function compactName(value: string, maximumLength = 42): string {
  const normalized = value.replace(/\s+/gu, " ").trim();
  if (!normalized) return "";
  return normalized.length > maximumLength
    ? `${normalized.slice(0, Math.max(1, maximumLength - 1)).trimEnd()}…`
    : normalized;
}

export function relationParticipants(
  relation: MessageRelationObservation,
  zh: boolean
): RelationParticipants {
  const unavailable = zh ? "发送者未记录" : "Sender unavailable";
  const targetUnavailable = zh ? "被回复者未记录" : "Reply target unavailable";
  const nonMessageTarget = zh ? "非消息目标" : "Non-message target";

  return {
    source: compactName(relation.source_author_display_name) || unavailable,
    target:
      relation.target_ref_type === "message"
        ? compactName(relation.target_author_display_name) || targetUnavailable
        : compactName(relation.target_author_display_name) || nonMessageTarget
  };
}

export function relationActionLabel(relation: MessageRelationObservation, zh: boolean): string {
  if (relation.relation_type === "REPLY_TO") return zh ? "回复" : "replied to";
  return relation.relation_type.replace(/_/gu, " ");
}
