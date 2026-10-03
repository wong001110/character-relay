import { roomRequest } from "./roomHttp";

export interface WebProfile { id: string; display_name: string; avatar_url: string; version: number }
export interface WebRoom { id: string; name: string; connection_id: string; guild_id: string; channel_id: string; thread_id: string; enabled: boolean; can_manage: boolean; can_post: boolean }
export interface WebMember { user_id: string; display_name: string; can_post: boolean }
export interface WebExpression { resource_key: string; resource_type: "emoji" | "sticker"; resource_id: string; name: string; animated: boolean; asset_url: string; format_type: string; description: string }
export interface WebAttachment { attachment_id: string; url: string; proxy_url: string; filename: string; description: string; content_type: string; size_bytes: number | null; width: number | null; height: number | null }
export interface WebMention { kind: "user" | "role" | "channel"; target_id: string; label: string }
export interface WebEmbed { embed_type: string; url: string; title: string; description: string; provider_name: string; author_name: string; image_url: string; image_proxy_url: string; thumbnail_url: string; thumbnail_proxy_url: string }
export interface WebPollAnswer { answer_id: number; text: string; emoji_name: string; emoji_id: string; vote_count: number }
export interface WebPoll { question: string; answers: WebPollAnswer[]; allow_multiselect: boolean; expires_at: string | null; results_finalized: boolean }
export interface WebReaction { key: string; resource_id: string; name: string; animated: boolean; asset_url: string; discord_count: number; web_count: number; count: number; mine: boolean; mine_profile_ids: string[] }
export interface WebReplyPreview { message_id: string; available: boolean; in_snapshot: boolean; display_name: string; summary: string }
export interface WebMessage { id: string; author_id: string; display_name: string; avatar_url: string; actor_type: string; text: string; deleted: boolean; content_available: boolean; created_at: string | null; edited_at: string | null; reply_to_message_id: string; reply_preview: WebReplyPreview | null; attachments: WebAttachment[]; custom_emojis: WebExpression[]; stickers: WebExpression[]; mentions: WebMention[]; embeds: WebEmbed[]; poll: WebPoll | null; reactions: WebReaction[]; pinned: boolean }
export interface WebOutbox { id: string; client_message_id: string; profile_id: string; display_name: string; avatar_url: string; text: string; reply_to_message_id: string; sticker_resource_key: string; status: "pending" | "claimed" | "delivered" | "failed" | "uncertain" | "cancelled"; discord_message_id: string; reason: string; created_at: string; routing_status: string }
export interface WebSnapshot { room_id: string; messages: WebMessage[]; outbox: WebOutbox[]; history_limit: number }
export interface WebSend { client_message_id: string; profile_id: string; text: string; reply_to_message_id: string; sticker_resource_key?: string }
export interface WebReactionInput { profile_id: string; emoji_key: string; emoji_name?: string }
export function snapshotForRoomTransition(current: WebSnapshot, roomId: string): WebSnapshot {
  if (current.room_id === roomId) return current;
  return {room_id: "", messages: [], outbox: [], history_limit: current.history_limit || 64};
}
const path = (id: string) => `/api/web-chat/rooms/${encodeURIComponent(id)}`;
export const webRoomApi = {
  rooms: () => roomRequest<WebRoom[]>("/api/web-chat/rooms"),
  profiles: () => roomRequest<WebProfile[]>("/api/web-chat/profiles"),
  profile: (data: Pick<WebProfile, "display_name" | "avatar_url">, existing?: WebProfile) =>
    roomRequest<WebProfile>(`/api/web-chat/profiles${existing ? `/${encodeURIComponent(existing.id)}` : ""}`, {method: existing ? "PATCH" : "POST", body: JSON.stringify({...data, ...(existing ? {expected_version: existing.version} : {})})}),
  publish: (data: Pick<WebRoom, "connection_id" | "guild_id" | "channel_id" | "thread_id" | "name">) => roomRequest<{id: string}>("/api/web-chat/rooms", {method: "POST", body: JSON.stringify(data)}),
  configure: (id: string, enabled: boolean) => roomRequest<void>(path(id), {method: "PATCH", body: JSON.stringify({enabled})}),
  members: (id: string) => roomRequest<WebMember[]>(`${path(id)}/members`),
  grant: (id: string, user_id: string, can_post: boolean) => roomRequest<void>(`${path(id)}/members`, {method: "PUT", body: JSON.stringify({user_id, can_post})}),
  revoke: (id: string, userId: string) => roomRequest<void>(`${path(id)}/members/${encodeURIComponent(userId)}`, {method: "DELETE"}),
  snapshot: (id: string) => roomRequest<WebSnapshot>(`${path(id)}/messages`),
  expressions: (id: string) => roomRequest<WebExpression[]>(`${path(id)}/expressions`),
  react: (id: string, messageId: string, data: WebReactionInput) => roomRequest<void>(
    `${path(id)}/messages/${encodeURIComponent(messageId)}/reactions`,
    {method: "PUT", body: JSON.stringify(data)}
  ),
  unreact: (id: string, messageId: string, data: WebReactionInput) => roomRequest<void>(
    `${path(id)}/messages/${encodeURIComponent(messageId)}/reactions`,
    {method: "DELETE", body: JSON.stringify(data)}
  ),
  send: (id: string, data: WebSend) => roomRequest<WebOutbox>(`${path(id)}/messages`, {
    method: "POST",
    body: JSON.stringify(data),
    signal: AbortSignal.timeout(15_000)
  }),
  eventsUrl: (id: string) => `${path(id)}/events`
};
/** A Discord echo and its local receipt are one visible message. Keep unresolved sends explicit. */
export function unmatchedOutbox(snapshot: WebSnapshot): WebOutbox[] {
  const ids = new Set(snapshot.messages.map(message => message.id));
  return snapshot.outbox.filter(item => !item.discord_message_id || !ids.has(item.discord_message_id));
}

/** Surface a successful POST immediately; SSE is convergence, not acknowledgement. */
export function withAcceptedOutbox(snapshot: WebSnapshot, roomId: string, accepted: WebOutbox): WebSnapshot {
  if (snapshot.room_id !== roomId) return snapshot;
  return {
    ...snapshot,
    outbox: [
      accepted,
      ...snapshot.outbox.filter(item =>
        item.id !== accepted.id && item.client_message_id !== accepted.client_message_id
      )
    ].slice(0, 32)
  };
}
