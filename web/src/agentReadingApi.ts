import { roomRequest } from "./roomHttp";
import type { WebMessage } from "./webRoomApi";

export interface AgentReadingItem {
  message_id: string; source_revision: number; room_revision: number;
  change: "new" | "edited" | "deleted" | "unavailable";
  state: "current" | "changed" | "removed"; message: WebMessage | null;
}
export interface AgentReadingBatch {
  id: string; from_revision: number; to_revision: number;
  gap_generation: number; needs_reread: boolean; items: AgentReadingItem[];
}
export interface AgentReadingStatus {
  room_id: string; profile_id: string; cursor_revision: number; observed_revision: number;
  pending_count: number; needs_reread: boolean; gap_generation: number;
  history_scope: "recorded_current_state"; batch: AgentReadingBatch | null;
}
export interface AgentReadingState {
  enabled: boolean; busy: boolean; localGap: boolean;
  status: AgentReadingStatus | null; error: string;
}
/** Reject unscoped/malformed state before any HTML is derived from it. */
export function validateAgentReadingStatus(status: AgentReadingStatus, room: string, profile: string): AgentReadingStatus {
  const integer = (value: unknown) => Number.isSafeInteger(value) && (value as number) >= 0;
  const messageValid = (message: WebMessage | null, id: string) => message !== null && typeof message === "object" &&
    message.id === id && typeof message.text === "string" && typeof message.display_name === "string" && typeof message.avatar_url === "string" && typeof message.actor_type === "string" &&
    typeof message.deleted === "boolean" && typeof message.content_available === "boolean" &&
    Array.isArray(message.attachments) && message.attachments.every(item => item && typeof item.filename === "string" && typeof item.content_type === "string" && typeof item.url === "string" && typeof item.proxy_url === "string" && typeof item.description === "string") &&
    Array.isArray(message.custom_emojis) && message.custom_emojis.every(item => item && typeof item.asset_url === "string" && typeof item.resource_id === "string") &&
    Array.isArray(message.mentions) && message.mentions.every(item => item && typeof item.target_id === "string" && typeof item.label === "string") &&
    Array.isArray(message.stickers) && message.stickers.every(item => item && typeof item.name === "string") &&
    Array.isArray(message.embeds) && message.embeds.every(item => item && [item.url, item.image_url, item.image_proxy_url, item.thumbnail_url, item.thumbnail_proxy_url, item.title, item.provider_name, item.description, item.embed_type].every(value => typeof value === "string")) &&
    (message.reply_preview === null || (typeof message.reply_preview === "object" && Boolean(message.reply_preview) && typeof message.reply_preview.message_id === "string" && typeof message.reply_preview.display_name === "string" && typeof message.reply_preview.summary === "string" && typeof message.reply_preview.available === "boolean" && typeof message.reply_preview.in_snapshot === "boolean")) &&
    (message.poll === null || (typeof message.poll === "object" && Boolean(message.poll) && typeof message.poll.question === "string"));
  if (!status || status.room_id !== room || status.profile_id !== profile || status.history_scope !== "recorded_current_state" ||
      !integer(status.cursor_revision) || !integer(status.observed_revision) || status.cursor_revision > status.observed_revision || !integer(status.pending_count) || !integer(status.gap_generation) || typeof status.needs_reread !== "boolean" ||
      (status.batch !== null && (!status.batch || typeof status.batch.id !== "string" || !status.batch.id || !integer(status.batch.from_revision) || !integer(status.batch.to_revision) || status.batch.to_revision < status.batch.from_revision || status.batch.to_revision > status.observed_revision ||
        !integer(status.batch.gap_generation) || status.batch.gap_generation > status.gap_generation || typeof status.batch.needs_reread !== "boolean" || !Array.isArray(status.batch.items) || status.batch.items.length > 64 ||
        !status.batch.items.every(item => item && typeof item.message_id === "string" && Boolean(item.message_id) && integer(item.room_revision) && integer(item.source_revision) &&
          ["new", "edited", "deleted", "unavailable"].includes(item.change) && ["current", "changed", "removed"].includes(item.state) &&
          (item.message === null || (item.state === "current" && messageValid(item.message, item.message_id))))))) throw new Error("invalid_agent_reading_status");
  return status;
}
const path = (room: string, profile: string) =>
  `/api/web-chat/rooms/${encodeURIComponent(room)}/agent-reading/${encodeURIComponent(profile)}`;
const post = (body: object): RequestInit => ({method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(15_000)});
export const agentReadingApi = {
  status: (room: string, profile: string) => roomRequest<AgentReadingStatus>(path(room, profile), {signal: AbortSignal.timeout(15_000), cache: "no-store"}),
  gap: (room: string, profile: string, eventId: string) => roomRequest<AgentReadingStatus>(`${path(room, profile)}/gap`, post({event_id: eventId})),
  batch: (room: string, profile: string) => roomRequest<AgentReadingStatus>(`${path(room, profile)}/batch`, post({})),
  complete: (room: string, profile: string, batchId: string) => roomRequest<AgentReadingStatus>(`${path(room, profile)}/complete`, post({batch_id: batchId}))
};
