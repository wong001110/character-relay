/** Web participants use a dedicated bot-owned webhook, never the browser's Discord credentials. */
import { randomUUID } from "node:crypto";
import { Client, WebhookClient, type Message } from "discord.js";
import { checkRoomAccess, rawRoomSource, roomLocation, type RoomEvidence } from "./roomEvidence.js";
import { safeDiagnosticError } from "./safeDiagnosticError.js";

export interface WebRoom {
  id: string; name: string; guild_id: string; channel_id: string; thread_id: string; webhook_id: string;
}
export interface WebClaim {
  id: string; room_id: string; claim_nonce: string; profile_id: string; actor_id: string;
  display_name: string; avatar_url: string; text: string; reply_to_message_id: string;
  guild_id: string; channel_id: string; thread_id: string; webhook_id: string;
  discord_message_id: string; created_at: string;
}
export interface WebAck {
  status: "delivered" | "failed" | "uncertain" | "cancelled";
  message_id?: string; webhook_id?: string; created_at?: string; reason?: string;
}
export interface WebBridgeTransport {
  webRooms(): Promise<WebRoom[]>;
  registerWebRoomWebhook(roomId: string, webhookId: string): Promise<void>;
  claimWebMessage(roomId: string, nonce: string): Promise<WebClaim | null>;
  preflightWebMessage(claim: WebClaim): Promise<{allowed: boolean}>;
  acknowledgeWebMessage(claim: WebClaim, result: WebAck): Promise<unknown>;
  webDispatch(): Promise<WebClaim[]>;
  finishWebDispatch(claim: WebClaim, outcome?: "processed" | "failed"): Promise<void>;
  observeRoom(input: RoomEvidence): Promise<unknown>;
}

export function webMessageText(claim: WebClaim): string {
  const reply = claim.reply_to_message_id
    ? `↪ https://discord.com/channels/${encodeURIComponent(claim.guild_id)}/${encodeURIComponent(claim.thread_id || claim.channel_id)}/${encodeURIComponent(claim.reply_to_message_id)}\n`
    : "";
  const content = `${reply}${claim.text}`;
  if (!claim.text.trim() || content.length > 2000) throw new Error("web_message_too_long_or_empty");
  return content;
}

/** Definitive HTTP rejection differs from a connection loss after Discord may have accepted. */
export function webSendFailure(error: unknown): WebAck {
  const status = error && typeof error === "object" && "status" in error ? Number(error.status) : 0;
  return status >= 400 && status < 500
    ? {status: "failed", reason: "discord_rejected"}
    : {status: "uncertain", reason: "discord_receipt_unavailable"};
}

/** Testable send transaction: ACK retry is allowed; sending twice is never an ACK repair. */
export async function deliverWebMessage(claim: WebClaim, transport: WebBridgeTransport, effects: {
  canSend: () => Promise<boolean>;
  send: (content: string) => Promise<{id: string; webhook_id: string; created_at: string}>;
}): Promise<void> {
  if (!(await effects.canSend()) || !(await transport.preflightWebMessage(claim)).allowed) {
    await transport.acknowledgeWebMessage(claim, {status: "cancelled", reason: "send_preflight_denied"});
    return;
  }
  let content: string;
  try { content = webMessageText(claim); }
  catch {
    await transport.acknowledgeWebMessage(claim, {status: "failed", reason: "message_invalid"});
    return;
  }
  let result: WebAck;
  try {
    const receipt = await effects.send(content);
    if (!receipt.id || receipt.webhook_id !== claim.webhook_id) throw new Error("invalid_send_receipt");
    result = {status: "delivered", message_id: receipt.id, webhook_id: receipt.webhook_id,
      created_at: receipt.created_at};
  } catch (error) { result = webSendFailure(error); }
  // Only retry persistence of the exact same receipt, never Execute Webhook.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try { await transport.acknowledgeWebMessage(claim, result); return; }
    catch (error) {
      if (attempt === 2) throw error;
      await new Promise(resolve => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
}

type RoomChannel = Message<true>["channel"];

export class WebRoomBridge {
  private rooms = new Map<string, WebRoom>();
  private readonly hooks = new Map<string, WebhookClient>();
  private readonly activeDispatch = new Set<string>();
  private readonly dispatchAttempts = new Map<string, number>();
  private readonly observed = new Set<string>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private running: Promise<void> | null = null;
  private refreshedAt = 0;

  constructor(private readonly client: Client, private readonly transport: WebBridgeTransport,
    private readonly contentIntent: boolean,
    private readonly onMessage: (message: Message<true>, claim: WebClaim) => Promise<void>,
    private readonly log: (message: string, detail: Record<string, unknown>) => void) {}

  hasRoom(guildId: string, channelId: string, threadId: string): boolean {
    return [...this.rooms.values()].some(r => r.guild_id === guildId && r.channel_id === channelId && r.thread_id === threadId);
  }

  private async channel(room: Pick<WebRoom, "guild_id" | "channel_id" | "thread_id">): Promise<RoomChannel> {
    const channel = await this.client.channels.fetch(room.thread_id || room.channel_id, {force: true});
    if (!channel || !channel.isTextBased() || channel.isDMBased() || !("guild" in channel) ||
        channel.guild.id !== room.guild_id || !("messages" in channel) ||
        (channel.isThread() ? channel.parentId !== room.channel_id || channel.id !== room.thread_id
          : Boolean(room.thread_id) || channel.id !== room.channel_id)) throw new Error("web_room_channel_unavailable");
    return channel as RoomChannel;
  }

  private async refresh(): Promise<void> {
    const rows = await this.transport.webRooms();
    this.rooms = new Map(rows.map(row => [row.id, row]));
    for (const [id, hook] of this.hooks) {
      if (!rows.some(room => room.webhook_id === id)) { hook.destroy(); this.hooks.delete(id); }
    }
    for (const room of rows) {
      try {
        const channel = await this.channel(room);
        const access = await checkRoomAccess({channel, guild: channel.guild});
        let messages: RoomEvidence["messages"] = [];
        if (access.readable && !this.observed.has(room.id)) {
          const history = await channel.messages.fetch({limit: 64, cache: false});
          messages = [...history.values()].filter((m): m is Message<true> => m.inGuild())
            .sort((a, b) => a.createdTimestamp - b.createdTimestamp)
            .map(m => rawRoomSource(m, this.contentIntent));
        }
        await this.transport.observeRoom({guild_id: room.guild_id, channel_id: room.channel_id,
          thread_id: room.thread_id, category_id: channel.isThread() ? channel.parent?.parentId ?? "" : channel.parentId ?? "",
          messages, readable: access.readable, permission_checked_at: access.checkedAt});
        if (access.readable) this.observed.add(room.id); else this.observed.delete(room.id);
        if (!access.writable) continue;
        const parent = channel.isThread() ? channel.parent : channel;
        if (!parent || !("fetchWebhooks" in parent) || !("createWebhook" in parent)) continue;
        const hooks = await parent.fetchWebhooks();
        let hook = hooks.find(h => h.id === room.webhook_id && h.owner?.id === this.client.user?.id);
        hook ??= hooks.find(h => h.name === "Character Relay Web" && h.owner?.id === this.client.user?.id);
        hook ??= await parent.createWebhook({name: "Character Relay Web", reason: "Explicitly published Character Relay web room"});
        if (!hook.token) throw new Error("web_room_webhook_unavailable");
        if (room.webhook_id !== hook.id) {
          await this.transport.registerWebRoomWebhook(room.id, hook.id);
          room.webhook_id = hook.id;
        }
        if (!this.hooks.has(hook.id)) this.hooks.set(hook.id,
          new WebhookClient({id: hook.id, token: hook.token}, {rest: {retries: 0, timeout: 15_000}}));
      } catch (error) {
        await this.transport.observeRoom({guild_id: room.guild_id, channel_id: room.channel_id,
          thread_id: room.thread_id, category_id: "", messages: [], readable: false,
          permission_checked_at: new Date().toISOString()}).catch(() => undefined);
        this.observed.delete(room.id);
        this.log("Web room transport could not refresh.", {roomId: room.id, ...safeDiagnosticError(error)});
      }
    }
  }

  private async tick(): Promise<void> {
    if (Date.now() - this.refreshedAt > 30_000) {
      await this.refresh(); this.refreshedAt = Date.now();
    }
    for (const room of this.rooms.values()) {
      if (this.stopped) return;
      const hook = this.hooks.get(room.webhook_id);
      if (!hook) continue;
      const claim = await this.transport.claimWebMessage(room.id, randomUUID());
      if (!claim) continue;
      await deliverWebMessage(claim, this.transport, {
        canSend: async () => {
          const channel = await this.channel(room);
          const access = await checkRoomAccess({channel, guild: channel.guild});
          if (!access.writable) return false;
          if (claim.reply_to_message_id) {
            const parent = await channel.messages.fetch({message: claim.reply_to_message_id, force: true, cache: false}).catch(() => null);
            if (!parent || parent.channelId !== (room.thread_id || room.channel_id)) return false;
          }
          return true;
        },
        send: async content => {
          // discord.js Execute Webhook requests wait=true and returns the actual Message receipt.
          const message = await hook.send({content, username: claim.display_name,
            ...(claim.avatar_url ? {avatarURL: claim.avatar_url} : {}),
            ...(room.thread_id ? {threadId: room.thread_id} : {}),
            allowedMentions: {parse: [], repliedUser: false}});
          return {id: message.id, webhook_id: message.webhook_id ?? "", created_at: message.timestamp};
        }
      });
    }
    const pending = await this.transport.webDispatch();
    for (const claim of pending) {
      if (this.activeDispatch.size >= 4) break;
      if (this.activeDispatch.has(claim.id)) continue;
      this.activeDispatch.add(claim.id);
      const task = async (): Promise<void> => {
        try {
          const channel = await this.channel(claim);
          const access = await checkRoomAccess({channel, guild: channel.guild});
          if (!access.readable) throw new Error("web_dispatch_room_unavailable");
          const message = await channel.messages.fetch({message: claim.discord_message_id, force: true, cache: false});
          if (!message.inGuild() || message.webhookId !== claim.webhook_id) throw new Error("web_dispatch_receipt_mismatch");
          await this.transport.observeRoom({...roomLocation(message), messages: [rawRoomSource(message, true)],
            readable: true, permission_checked_at: access.checkedAt});
          await this.onMessage(message, claim);
          await this.transport.finishWebDispatch(claim);
          this.dispatchAttempts.delete(claim.id);
        } catch (error) {
          const count = (this.dispatchAttempts.get(claim.id) ?? 0) + 1;
          this.dispatchAttempts.set(claim.id, count);
          this.log("Delivered Web message processing failed; it will not be sent again.", {outboxId: claim.id, ...safeDiagnosticError(error)});
          if (count >= 3) await this.transport.finishWebDispatch(claim, "failed").catch(() => undefined);
        } finally { this.activeDispatch.delete(claim.id); }
      };
      void task();
    }
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    const loop = (): void => {
      if (this.stopped) return;
      this.running = this.tick().catch(error => this.log("Web room bridge iteration failed.", safeDiagnosticError(error))).finally(() => {
        if (!this.stopped) this.timer = setTimeout(loop, 1_000);
      });
    };
    loop();
  }

  async stop(): Promise<void> {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    await this.running;
    for (const hook of this.hooks.values()) hook.destroy();
    this.hooks.clear();
  }
}
