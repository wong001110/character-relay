/** Raw Discord evidence. No semantic segmentation, model calls, or cross-room ancestry. */
import { ChannelType,PermissionFlagsBits,type Message } from "discord.js";
import { createHash } from "node:crypto";
import type { DiscordContextMessage } from "./types.js";

export interface RoomLocation {
  guild_id: string;
  channel_id: string;
  thread_id: string;
  category_id: string;
}

export interface RoomSource {
  message_id: string;
  channel_id: string;
  thread_id: string;
  author_id: string;
  author_display_name: string;
  author_avatar_url?: string;
  webhook_id?: string;
  author_is_bot: boolean;
  author_deployment_id: string;
  text: string;
  reply_to_message_id: string;
  created_at: string | null;
  edited_at: string | null;
  deleted: boolean;
  content_available: boolean;
  has_unseen_media: boolean;
  media_fingerprint?: string;
}

export interface RoomEvidence extends RoomLocation {
  messages: RoomSource[];
  readable: boolean;
  permission_checked_at: string;
}

export interface RoomChoice {
  deployment_id: string;
  target_message_id: string;
  selection_id: string;
  mode: string;
}

export interface RoomRoutingResult {
  outcome: "direct" | "decision" | "none" | "blocked" | "unavailable" | "invalid";
  reason: string;
  choices: RoomChoice[];
  route_id: string;
  snapshot_revision: number;
  prompt_version: string;
  input_fingerprint: string;
  attempts: Array<{
    provider: string; model: string; outcome: string; latency_ms: number;
    input_tokens: number | null; output_tokens: number | null; cost_usd: number | null;
  }>;
}

export interface RoomRoutingRequest extends RoomEvidence {
  request_id: string;
  trigger_message_id: string;
  deployment_ids: string[];
  explicit_deployment_ids: string[];
  action_actor_id?: string;
  action_target_message_id?: string;
  ambient_requested: boolean;
}

export function roomLocation(message: Message<true>): RoomLocation {
  const channel = message.channel;
  return {
    guild_id: message.guildId,
    channel_id: channel.isThread() ? channel.parentId ?? "" : channel.id,
    thread_id: channel.isThread() ? channel.id : "",
    category_id: channel.isThread() ? channel.parent?.parentId ?? "" : channel.parentId ?? ""
  };
}

export function rawRoomSource(message: Message<true>, contentIntent: boolean): RoomSource {
  const location = roomLocation(message);
  const contentAvailable = contentIntent || Boolean(message.content) ||
    message.author.id === message.client.user.id ||
    message.mentions.users.has(message.client.user.id) ||
    Boolean(message.attachments.size || message.stickers.size || message.embeds.length);
  return {
    message_id: message.id,
    channel_id: location.channel_id,
    thread_id: location.thread_id,
    author_id: message.author.id,
    author_display_name: message.member?.displayName ?? message.author.globalName ?? message.author.username,
    author_avatar_url: message.author.displayAvatarURL?.() ?? "",
    webhook_id: message.webhookId ?? "",
    author_is_bot: message.author.bot,
    // Backend verifies canonical message-route identity; don't promote a webhook display name.
    author_deployment_id: "",
    text: contentAvailable ? message.content.slice(0, 10_000) : "",
    reply_to_message_id: message.reference?.channelId === message.channelId ||
      !message.reference?.channelId ? message.reference?.messageId ?? "" : "",
    created_at: message.createdAt.toISOString(),
    edited_at: message.editedAt?.toISOString() ?? null,
    deleted: false,
    content_available: contentAvailable,
    has_unseen_media: Boolean(message.attachments.size || message.embeds.length || message.stickers.size),
    media_fingerprint: createHash("sha256").update(JSON.stringify({
      attachments: [...message.attachments.values()].map(a => [a.id, a.name, a.size, a.contentType]),
      stickers: [...message.stickers.keys()],
      embeds: message.embeds.map(e => [e.title, e.description, e.fields,
        e.image?.url?.split("?")[0], e.thumbnail?.url?.split("?")[0]])
    })).digest("hex")
  };
}

export function sourceContext(source: RoomSource): DiscordContextMessage {
  return {
    message_id: source.message_id, channel_id: source.channel_id, thread_id: source.thread_id,
    author_id: source.author_id, author_display_name: source.author_display_name,
    author_deployment_id: source.author_deployment_id,
    is_bot: source.author_is_bot, text: source.text,
    reply_to_message_id: source.reply_to_message_id,
    ...(source.created_at ? { created_at: source.created_at } : {}),
    ...(source.edited_at ? { edited_at: source.edited_at } : {}),
    content_available: source.content_available, emojis: [], stickers: []
  };
}

export function sourceInRoom(source: RoomSource, room: RoomLocation): boolean {
  return source.channel_id === room.channel_id && source.thread_id === room.thread_id;
}

/** The adapter supplies only fresh permission observations and a same-channel fetcher. */
export async function collectEvidence(input: {
  room: RoomLocation;
  trigger: RoomSource;
  recent: readonly RoomSource[];
  readable: boolean;
  checkedAt: string;
  fetchSameRoom: (id: string) => Promise<RoomSource | null>;
  maximumAncestors?: number;
}): Promise<RoomEvidence> {
  const output: RoomEvidence = {
    ...input.room, messages: [], readable: input.readable, permission_checked_at: input.checkedAt
  };
  if (!input.readable) return output;
  if (!sourceInRoom(input.trigger, input.room)) throw new Error("source_scope_mismatch");
  const sources = new Map<string, RoomSource>();
  // Raw primary + its nearest ancestors always take precedence over unrelated recent history.
  sources.set(input.trigger.message_id, input.trigger);
  let current = input.trigger;
  const maximum = Math.max(0, Math.min(8, input.maximumAncestors ?? 8));
  for (let index = 0; index < maximum && current.reply_to_message_id; index += 1) {
    const id = current.reply_to_message_id;
    if (sources.has(id)) break;
    const parent = await input.fetchSameRoom(id);
    if (!parent) break;
    if (parent.message_id !== id || !sourceInRoom(parent, input.room)) {
      throw new Error("ancestor_scope_mismatch");
    }
    sources.set(id, parent);
    if (parent.deleted || !parent.content_available) break;
    current = parent;
  }
  for (const source of input.recent.slice(-24)) {
    if (sourceInRoom(source, input.room) && !sources.has(source.message_id)) {
      sources.set(source.message_id, source);
    }
  }
  output.messages = [...sources.values()].sort((a, b) =>
    (a.created_at ?? "").localeCompare(b.created_at ?? "") || a.message_id.localeCompare(b.message_id));
  return output;
}

/** SDK permission calculation + current private-thread membership, without joining a Thread. */
export async function checkRoomAccess(source: Pick<Message<true>, "channel" | "guild">): Promise<{
  readable: boolean; writable: boolean; checkedAt: string;
}> {
  try {
    const channel = await source.channel.fetch();
    const me = await source.guild.members.fetchMe({ force: true });
    const permissions = channel.permissionsFor(me);
    let readable = Boolean(permissions?.has([
      PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory
    ]));
    if (channel.isThread() && channel.type === ChannelType.PrivateThread &&
        !permissions?.has(PermissionFlagsBits.ManageThreads)) {
      const membership = await channel.members.fetchMe({ force: true }).catch(() => null);
      readable = readable && membership?.id === me.id;
    }
    const writable = readable && Boolean(permissions?.has(channel.isThread()
      ? PermissionFlagsBits.SendMessagesInThreads : PermissionFlagsBits.SendMessages)) &&
      (!channel.isThread() || !channel.locked || Boolean(permissions?.has(PermissionFlagsBits.ManageThreads)));
    return { readable, writable, checkedAt: new Date().toISOString() };
  } catch {
    // Unknown access is not a grant and must not fall back to cached private content.
    return { readable: false, writable: false, checkedAt: new Date().toISOString() };
  }
}

export async function discordEvidence(source: Message<true>, contentIntent: boolean): Promise<RoomEvidence> {
  const access = await checkRoomAccess(source);
  const room = roomLocation(source);
  if (!access.readable) return { ...room, messages: [], readable: false, permission_checked_at: access.checkedAt };
  // Bounded current history also rehydrates a restarted Connector. The SDK handles rate limits.
  const recent = await source.channel.messages.fetch({ limit: 24, cache: false });
  const primary = await source.channel.messages.fetch({ message: source.id, force: true, cache: false });
  return collectEvidence({
    room, trigger: rawRoomSource(primary, contentIntent),
    recent: [...recent.values()].filter((item): item is Message<true> => item.inGuild())
      .map(item => rawRoomSource(item, contentIntent)),
    readable: access.readable, checkedAt: access.checkedAt,
    fetchSameRoom: async id => {
      try {
        const parent = await source.channel.messages.fetch({ message: id, force: true, cache: false });
        if (!parent.inGuild() || parent.guildId !== source.guildId || parent.channelId !== source.channelId) {
          throw new Error("ancestor_scope_mismatch");
        }
        return rawRoomSource(parent, contentIntent);
      } catch (error) {
        // An inaccessible/missing Reply ancestor remains missing; never search the whole guild.
        if (typeof error === "object" && error && "code" in error &&
            [10008, 50001, 50013].includes(Number(error.code))) return null;
        throw error;
      }
    }
  });
}
