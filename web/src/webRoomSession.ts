import { RoomRequestError } from "./roomHttp";
import { webRoomApi, webRoomCanSubmit, withAcceptedOutbox, type WebRoom, type WebProfile, type WebSnapshot, type WebSend, type WebUpload } from "./webRoomApi";

export type LocalSubmission = {
  room: string; payload: WebSend; phase: "submitting" | "unknown";
  displayName: string; avatarUrl: string; attachments: WebUpload[];
};
export type AgentReadingState = {enabled: boolean; pendingCount: number};

export interface WebRoomSessionState {
  authenticated: boolean;
  roomId: string; rooms: WebRoom[]; profiles: WebProfile[]; profileId: string;
  snapshot: WebSnapshot; connection: string; unread: number;
  text: string; reply: string; attachments: WebUpload[]; stickerResourceKey: string;
  localSubmission: LocalSubmission | null; busy: boolean; error: string; demoMode: boolean;
  agentReading?: AgentReadingState;
}
const emptySnapshot = (): WebSnapshot => ({room_id: "", messages: [], outbox: [], history_limit: 64});
const initialState = (): WebRoomSessionState => ({authenticated: false, roomId: "", rooms: [], profiles: [], profileId: "", snapshot: emptySnapshot(), connection: "disconnected", unread: 0, text: "", reply: "", attachments: [], stickerResourceKey: "", localSubmission: null, busy: false, error: "", demoMode: false});
type Stream = Pick<EventSource, "addEventListener" | "close" | "onerror">;

/** One authenticated Portal session; subscribers are presentations, never transport owners. */
export class WebRoomSession {
  private state = initialState();
  private listeners = new Set<() => void>();
  private readers = new Map<string, boolean>();
  private identity = "";
  private generation = 0;
  private stream: Stream | null = null;
  private loaded = false;
  private loading: Promise<void> | null = null;
  private checkingAccess = false;
  private restoration: {identity: string; roomId: string} | null = null;
  private agentSeen: Set<string> | null = null;
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  private rolloverTimer: ReturnType<typeof setTimeout> | null = null;
  private rolloverDeadline = 0;
  private rolloverErrorSeen = false;
  private browserOnline = true;
  constructor(private api = webRoomApi, private createStream: (url: string) => Stream = url => new EventSource(url)) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  patch = (next: Partial<WebRoomSessionState>) => {
    const scopeChanged = (next.profileId !== undefined && next.profileId !== this.state.profileId) || (next.roomId !== undefined && next.roomId !== this.state.roomId);
    this.state = {...this.state, ...next};
    if (scopeChanged && this.state.agentReading?.enabled) this.resetAgentReading();
    for (const listener of this.listeners) listener();
  };
  configure(identity: string, demoMode: boolean) {
    this.restoration = null;
    if (identity !== this.identity) {
      this.generation++;
      this.agentSeen = null;
      this.stopStream();
      this.identity = identity;
      this.loaded = false;
      this.loading = null;
      this.readers.clear();
      this.clearPreviews();
      this.state = initialState();
      this.patch({demoMode, authenticated: Boolean(identity)});
    } else if (this.state.demoMode !== demoMode) {
      if (demoMode) this.setAgentReading(false);
      this.patch({demoMode});
    }
  }
  private stopStream() {
    if (this.heartbeatTimer) clearTimeout(this.heartbeatTimer);
    if (this.rolloverTimer) clearTimeout(this.rolloverTimer);
    this.heartbeatTimer = this.rolloverTimer = null;
    this.rolloverDeadline = 0;
    this.rolloverErrorSeen = false;
    this.stream?.close();
    this.stream = null;
    this.checkingAccess = false;
  }
  dispose() { this.configure("", false); this.stopStream(); }
  suspend() {
    const previous = {identity: this.identity, roomId: this.state.roomId};
    this.dispose();
    this.restoration = previous;
  }
  async restore(identity: string, demoMode: boolean) {
    const previous = this.restoration;
    this.configure(identity, demoMode);
    if (previous?.identity === identity) this.selectRoom(previous.roomId);
    await this.ensureLoaded();
  }
  private clearPreviews() {
    for (const file of this.state.attachments) if (file.preview_url) URL.revokeObjectURL(file.preview_url);
  }
  scope() { return {identity: this.identity, generation: this.generation}; }
  current(scope: {identity: string; generation: number}) { return this.identity === scope.identity && this.generation === scope.generation; }
  report(reason: unknown) {
    if (!this.denied(reason)) this.patch({error: reason instanceof Error ? reason.message : "request_failed"});
  }
  private denied(reason: unknown) {
    if (reason instanceof RoomRequestError && reason.status === 401) {
      this.configure("", false);
      return true;
    }
    if (reason instanceof RoomRequestError && reason.message === "room_unavailable") {
      this.selectRoom("");
      return true;
    }
    return false;
  }
  async ensureLoaded() {
    if (!this.identity || this.loaded) return;
    if (this.loading) return this.loading;
    const identity = this.identity;
    const promise = this.refresh().finally(() => { if (this.identity === identity && this.loading === promise) this.loading = null; });
    this.loading = promise;
    return promise;
  }
  async refresh() {
    if (!this.identity) return;
    const scope = this.scope();
    try {
      const [rooms, profiles] = await Promise.all([this.api.rooms(), this.api.profiles()]);
      if (!this.current(scope)) return;
      const previous = this.state.rooms.find(room => room.id === this.state.roomId);
      this.loaded = true;
      this.patch({rooms, profiles, profileId: profiles.some(item => item.id === this.state.profileId) ? this.state.profileId : profiles[0]?.id ?? ""});
      const next = rooms.find(room => room.id === this.state.roomId);
      if (this.state.roomId && !next) this.selectRoom("");
      else if (next && (!previous || previous.enabled !== next.enabled)) this.connect();
    } catch (reason) {
      if (this.current(scope) && !this.denied(reason)) this.report(reason);
    }
  }
  selectRoom(roomId: string) {
    if (this.state.roomId === roomId) return;
    this.generation++;
    this.clearPreviews();
    this.patch({roomId, snapshot: emptySnapshot(), reply: "", text: "", attachments: [], stickerResourceKey: "", localSubmission: null, unread: 0, error: "", busy: false});
    this.connect();
  }
  reconnect() { this.agentSeen = null; this.connect(); }
  setOnline(online: boolean) {
    if (online === this.browserOnline) return;
    this.browserOnline = online;
    if (!online) {
      this.agentSeen = null;
      this.stopStream();
      this.patch({connection: "disconnected"});
    } else {
      this.connect();
    }
  }
  private connect() {
    this.stopStream();
    const room = this.state.rooms.find(item => item.id === this.state.roomId);
    this.patch({connection: room?.enabled && this.identity && this.browserOnline ? "connecting" : "disconnected"});
    if (!room?.enabled || !this.identity || !this.browserOnline) return;
    const scope = this.scope();
    const stream = this.createStream(this.api.eventsUrl(room.id));
    this.stream = stream;
    const valid = () => this.current(scope) && this.stream === stream;
    stream.addEventListener("snapshot", event => {
      if (!valid()) return;
      try {
        const next: WebSnapshot = JSON.parse((event as MessageEvent<string>).data);
        if (next.room_id !== room.id || !Array.isArray(next.messages) || !Array.isArray(next.outbox)) throw new Error("invalid_room_snapshot");
        if ((next.source_revision !== undefined) && (!Number.isSafeInteger(next.source_revision) || next.source_revision! < 0)) throw new Error("invalid_room_snapshot");
        const previous = this.state.snapshot;
        const ids = new Set(previous.messages.map(item => item.id));
        const added = previous.room_id === next.room_id ? next.messages.filter(item => !ids.has(item.id)).length : 0;
        const reading = [...this.readers.values()].some(Boolean);
        const pending = this.state.localSubmission;
        const acknowledged = pending && next.outbox.some(item => item.client_message_id === pending.payload.client_message_id);
        if (acknowledged) this.clearPreviews();
        const agentReading = this.countAgentMessages(next);
        this.patch({...(agentReading ? {agentReading} : {}), snapshot: next, connection: "connected", unread: reading ? 0 : this.state.unread + added,
          ...(acknowledged ? {localSubmission: null, text: "", reply: "", attachments: [], stickerResourceKey: ""} : {})});
        this.agentTransportHealthy();
      } catch {
        stream.close();
        this.agentSeen = null;
        this.patch({snapshot: emptySnapshot(), unread: 0, error: "invalid_room_snapshot", connection: "unavailable"});
      }
    });
    stream.addEventListener("revoked", event => {
      if (valid()) {
        try {
          if (JSON.parse((event as MessageEvent<string>).data).reason === "session_revoked") {
            this.configure("", false);
            return;
          }
        } catch { /* Room revocation still clears the scoped transcript. */ }
        this.patch({rooms: this.state.rooms.filter(item => item.id !== room.id)});
        this.selectRoom("");
      }
    });
    stream.addEventListener("unavailable", () => {
      if (!valid()) return;
      stream.close();
      this.agentSeen = null;
      this.patch({connection: "unavailable"});
    });
    stream.addEventListener("heartbeat", () => { if (valid()) this.agentTransportHealthy(); });
    stream.addEventListener("rollover", () => {
      if (!valid()) return;
      this.rolloverDeadline = Date.now() + 5_000;
      this.rolloverErrorSeen = false;
      if (this.rolloverTimer) clearTimeout(this.rolloverTimer);
      this.rolloverTimer = setTimeout(() => {
        this.rolloverTimer = null;
        if (valid()) { this.agentSeen = null; this.patch({connection: "reconnecting"}); }
      }, 5_000);
    });
    stream.onerror = () => {
      if (!valid()) return;
      const expected = this.rolloverDeadline > Date.now() && !this.rolloverErrorSeen;
      this.rolloverErrorSeen = true;
      if (!expected) this.agentSeen = null;
      this.patch({connection: "reconnecting"});
      // SSE rollover is normal. A failed reopen may instead be auth loss; verify once
      // per outstanding request without treating every reconnect as revoked access.
      if (!this.checkingAccess) {
        this.checkingAccess = true;
        void this.refresh().finally(() => { if (valid()) this.checkingAccess = false; });
      }
    };
  }
  setReader(id: string, atLatest: boolean) {
    this.readers.set(id, atLatest);
    if (atLatest) this.markRead();
  }
  removeReader(id: string) { this.readers.delete(id); }
  markRead() { if (this.state.unread) this.patch({unread: 0}); }

  /** Session-only reminders. Viewing and human unread never clear this count. */
  setAgentReading(enabled: boolean) {
    if (enabled && (!this.identity || this.state.demoMode || !this.state.roomId || !this.state.profileId)) return;
    if (Boolean(this.state.agentReading?.enabled) === enabled) return;
    this.agentSeen = null;
    this.patch({agentReading: {enabled, pendingCount: 0}});
    if (enabled) {
      this.resetAgentReading();
      this.armAgentWatchdog();
    } else if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }
  private resetAgentReading() {
    // Joining with a current snapshot treats it as context, never historical work.
    this.agentSeen = this.state.snapshot.room_id === this.state.roomId && this.state.connection === "connected"
      ? new Set(this.state.snapshot.messages.map(message => message.id)) : null;
    this.state = {...this.state, agentReading: {enabled: true, pendingCount: 0}};
  }
  private countAgentMessages(next: WebSnapshot): AgentReadingState | undefined {
    const reading = this.state.agentReading;
    if (!reading?.enabled) return undefined;
    if (!this.agentSeen) {
      this.agentSeen = new Set(next.messages.map(message => message.id));
      return reading;
    }
    let added = 0;
    for (const message of next.messages) {
      if (this.agentSeen.has(message.id)) continue;
      this.agentSeen.add(message.id);
      if (!message.deleted && !(message.actor_type === "web_participant" && message.author_id === `web:${this.state.profileId}`)) added++;
    }
    // Bounded ID-only deduplication for the latest-64 transport; no message archive.
    while (this.agentSeen.size > 512) this.agentSeen.delete(this.agentSeen.values().next().value!);
    return {...reading, pendingCount: reading.pendingCount + added};
  }
  clearAgentReminders() {
    if (this.state.agentReading?.enabled) this.patch({agentReading: {...this.state.agentReading, pendingCount: 0}});
  }
  private agentTransportHealthy() {
    if (!this.browserOnline) return;
    if (this.rolloverTimer) clearTimeout(this.rolloverTimer);
    this.rolloverTimer = null;
    this.rolloverDeadline = 0;
    this.rolloverErrorSeen = false;
    if (!this.state.agentReading?.enabled) return;
    if (this.state.snapshot.room_id === this.state.roomId && this.state.connection === "reconnecting") this.patch({connection: "connected"});
    this.armAgentWatchdog();
  }
  private armAgentWatchdog() {
    if (this.heartbeatTimer) clearTimeout(this.heartbeatTimer);
    if (!this.state.agentReading?.enabled || this.state.connection !== "connected") return;
    this.heartbeatTimer = setTimeout(() => {
      this.heartbeatTimer = null;
      this.agentSeen = null;
      this.connect();
    }, 15_000);
  }
  async send() {
    const state = this.state;
    const room = state.rooms.find(item => item.id === state.roomId);
    const profile = state.profiles.find(item => item.id === state.profileId);
    if (!this.identity || state.demoMode || !room?.enabled || !room.can_post || !profile || !webRoomCanSubmit(state.connection) || state.busy || state.localSubmission || (!state.text.trim() && !state.attachments.length && !state.stickerResourceKey)) return;
    const pending: LocalSubmission = {room: room.id, payload: {client_message_id: crypto.randomUUID(), profile_id: profile.id, text: state.text, reply_to_message_id: state.reply, sticker_resource_key: state.stickerResourceKey, attachment_ids: state.attachments.map(item => item.id)}, phase: "submitting", displayName: profile.display_name, avatarUrl: profile.avatar_url, attachments: [...state.attachments]};
    await this.dispatch(pending);
  }
  async retry() {
    const state = this.state;
    const room = state.rooms.find(item => item.id === state.roomId);
    if (this.identity && !state.demoMode && !state.busy && room?.can_post && room.enabled && webRoomCanSubmit(state.connection) && state.localSubmission?.phase === "unknown") await this.dispatch(state.localSubmission);
  }
  private async dispatch(pending: LocalSubmission) {
    const scope = this.scope();
    this.patch({busy: true, error: "", localSubmission: {...pending, phase: "submitting"}});
    try {
      const accepted = await this.api.send(pending.room, pending.payload);
      if (!this.current(scope)) return;
      // SSE may already have acknowledged this exact client ID and advanced or
      // retired its receipt. A late POST response must not restore stale pending state.
      if (this.state.localSubmission?.payload.client_message_id === pending.payload.client_message_id) {
        this.clearPreviews();
        this.patch({snapshot: withAcceptedOutbox(this.state.snapshot, pending.room, accepted), localSubmission: null, text: "", reply: "", stickerResourceKey: "", attachments: []});
      }
    } catch (reason) {
      if (!this.current(scope)) return;
      if (!this.denied(reason) && this.state.localSubmission?.payload.client_message_id === pending.payload.client_message_id) {
        this.patch({localSubmission: {...pending, phase: "unknown"}});
        this.report(reason);
      }
    } finally { if (this.current(scope)) this.patch({busy: false}); }
  }
  async addAttachments(files: Iterable<File> | null) {
    const state = this.state;
    const room = state.rooms.find(item => item.id === state.roomId);
    if (!this.identity || !room?.can_post || state.demoMode || state.busy || state.localSubmission || !files) return;
    const selected = [...files];
    if (state.attachments.length + selected.length > 4) { this.report(new Error("attachment_limit_exceeded")); return; }
    const scope = this.scope();
    this.patch({busy: true, error: ""});
    try {
      for (const file of selected) {
        try {
          const uploaded = await this.api.uploadAttachment(room.id, file);
          if (!this.current(scope)) return;
          const preview = uploaded.mime_type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
          this.patch({attachments: [...this.state.attachments, {...uploaded, ...(preview ? {preview_url: preview} : {})}]});
        } catch (reason) {
          if (!this.current(scope) || this.denied(reason)) return;
          this.report(reason);
        }
      }
    } finally { if (this.current(scope)) this.patch({busy: false}); }
  }
  removeAttachment(id: string) {
    const removed = this.state.attachments.find(item => item.id === id);
    if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
    this.patch({attachments: this.state.attachments.filter(item => item.id !== id)});
  }
}
