/** Current SDK evidence + the server's persisted draft. No local model, tools, or cursor authority. */
import type { Message } from "discord.js";
import { checkRoomAccess, collectEvidence, rawRoomSource, roomLocation, type RoomEvidence,
  type RoomSource } from "./roomEvidence.js";
import type { DiscordReply, DiscordSocialTurnCursor } from "./types.js";

export interface DraftPreflightRequest extends RoomEvidence {
  operation_id: string;
  step_id: string;
  writable: boolean;
}

export interface DraftPreflightResult {
  disposition: "keep" | "refreshed" | "drop" | "blocked" | "in_progress";
  reason: string;
  reply: DiscordReply | null;
  cursor: DiscordSocialTurnCursor | null;
}

export interface DraftTransport {
  preflightDraft(body: DraftPreflightRequest): Promise<DraftPreflightResult>;
}

type Access = { readable: boolean; writable: boolean; checkedAt: string };
export interface DraftEvidencePort {
  checkAccess(): Promise<Access>;
  read(id: string): Promise<RoomSource | null>;
  recent(): Promise<RoomSource[]>;
}

/** Exposed as a small port for deterministic deletion/revocation/race tests. */
export async function currentDraftEvidence(
  room: ReturnType<typeof roomLocation>, reply: DiscordReply, port: DraftEvidencePort
): Promise<RoomEvidence & { writable: boolean }> {
  let access = await port.checkAccess();
  const denied = (): RoomEvidence & { writable: boolean } => ({
    ...room, messages: [], readable: false, writable: false,
    permission_checked_at: access.checkedAt
  });
  if (!access.readable) return denied();
  const target = reply.context_trace?.source_target_message_id;
  if (!target) throw new Error("draft_source_binding_missing");
  const tombstone = (id: string): RoomSource => ({
    message_id: id, channel_id: room.channel_id, thread_id: room.thread_id,
    author_id: "", author_display_name: "", author_is_bot: false, author_deployment_id: "",
    text: "", reply_to_message_id: "", created_at: null, edited_at: null,
    deleted: true, content_available: false, has_unseen_media: false
  });
  const primary = await port.read(target) ?? tombstone(target);
  const evidence = await collectEvidence({
    room, trigger: primary, recent: await port.recent(), readable: true,
    checkedAt: access.checkedAt, fetchSameRoom: port.read
  });
  const known = new Map(evidence.messages.map(item => [item.message_id, item]));
  // Re-read previously used inputs, not just the newest window. A deleted ancestor or
  // displaced input must not survive as a plausible draft sourced from an old cache.
  const ids = Object.keys(reply.context_trace?.source_revisions ?? {}).slice(0, 30);
  for (let offset = 0; offset < ids.length; offset += 4) {
    const batch = await Promise.all(ids.slice(offset, offset + 4).map(async id =>
      [id, await port.read(id) ?? tombstone(id)] as const));
    for (const [id, item] of batch) {
      if (item.message_id !== id || item.channel_id !== room.channel_id || item.thread_id !== room.thread_id) {
        throw new Error("draft_source_scope_mismatch");
      }
      known.set(id, item);
    }
  }
  access = await port.checkAccess();
  if (!access.readable) return denied();
  return { ...evidence, messages: [...known.values()].slice(0, 64),
    permission_checked_at: access.checkedAt, writable: access.writable };
}

export async function preflightDiscordDraft(input: {
  source: Message<true>; reply: DiscordReply; transport: DraftTransport;
  operationId: string; stepId: string; contentIntent: boolean;
}): Promise<DraftPreflightResult> {
  const { source, reply } = input;
  const room = roomLocation(source);
  const read = async (id: string): Promise<RoomSource | null> => {
    try {
      const message = await source.channel.messages.fetch({ message: id, force: true, cache: false });
      if (!message.inGuild() || message.guildId !== source.guildId || message.channelId !== source.channelId) {
        throw new Error("draft_source_scope_mismatch");
      }
      return rawRoomSource(message, input.contentIntent);
    } catch (error) {
      if (typeof error === "object" && error && "code" in error && Number(error.code) === 10008) return null;
      // Access/network failures are not proof of deletion and never use cached private text.
      throw error;
    }
  };
  const evidence = await currentDraftEvidence(room, reply, {
    checkAccess: () => checkRoomAccess(source), read,
    recent: async () => [...(await source.channel.messages.fetch({ limit: 24, cache: false })).values()]
      .filter((message): message is Message<true> => message.inGuild())
      .map(message => rawRoomSource(message, input.contentIntent))
  });
  const body = { ...evidence, operation_id: input.operationId, step_id: input.stepId };
  let result = await input.transport.preflightDraft(body);
  if (result.disposition === "keep" || result.disposition === "refreshed") {
    // The Character may have spent time revising; a pre-model permission check is not enough.
    const access = await checkRoomAccess(source);
    if (!access.readable || !access.writable) {
      result = await input.transport.preflightDraft({ ...body, messages: [],
        readable: access.readable, writable: access.writable, permission_checked_at: access.checkedAt });
    }
  }
  if (result.reply && (result.reply.deployment_id !== reply.deployment_id ||
      result.reply.context_trace?.source_target_message_id !== reply.context_trace?.source_target_message_id)) {
    throw new Error("draft_response_binding_mismatch");
  }
  return result;
}
