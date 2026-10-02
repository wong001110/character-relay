import { roomRequest } from "./roomHttp";

export interface WebProfile { id: string; display_name: string; avatar_url: string; version: number }
export interface WebRoom { id: string; name: string; connection_id: string; guild_id: string; channel_id: string; thread_id: string; enabled: boolean; can_manage: boolean; can_post: boolean }
export interface WebMember { user_id: string; display_name: string; can_post: boolean }
export interface WebMessage { id: string; author_id: string; display_name: string; avatar_url: string; actor_type: string; text: string; deleted: boolean; content_available: boolean; created_at: string | null; edited_at: string | null; reply_to_message_id: string }
export interface WebOutbox { id: string; client_message_id: string; profile_id: string; display_name: string; avatar_url: string; text: string; reply_to_message_id: string; status: "pending" | "claimed" | "delivered" | "failed" | "uncertain" | "cancelled"; discord_message_id: string; reason: string; created_at: string; routing_status: string }
export interface WebSnapshot { room_id: string; messages: WebMessage[]; outbox: WebOutbox[]; history_limit: number }
export interface WebSend { client_message_id: string; profile_id: string; text: string; reply_to_message_id: string }
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
  send: (id: string, data: WebSend) => roomRequest<WebOutbox>(`${path(id)}/messages`, {method: "POST", body: JSON.stringify(data)}),
  eventsUrl: (id: string) => `${path(id)}/events`
};
/** A Discord echo and its local receipt are one visible message. Keep unresolved sends explicit. */
export function unmatchedOutbox(snapshot: WebSnapshot): WebOutbox[] {
  const ids = new Set(snapshot.messages.map(message => message.id));
  return snapshot.outbox.filter(item => !item.discord_message_id || !ids.has(item.discord_message_id));
}
