import { RoomRequestError } from "./roomHttp";
import { webRoomApi, webRoomCanSubmit, withAcceptedOutbox, type WebRoom, type WebProfile, type WebSnapshot, type WebSend, type WebUpload } from "./webRoomApi";

export type LocalSubmission = {
  room: string; payload: WebSend; phase: "submitting" | "unknown";
  displayName: string; avatarUrl: string; attachments: WebUpload[];
};
export interface WebRoomSessionState {
  authenticated: boolean;
  roomId: string; rooms: WebRoom[]; profiles: WebProfile[]; profileId: string;
  snapshot: WebSnapshot; connection: string; unread: number;
  text: string; reply: string; attachments: WebUpload[]; stickerResourceKey: string;
  localSubmission: LocalSubmission | null; busy: boolean; error: string; demoMode: boolean;
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
  constructor(private api = webRoomApi, private createStream: (url: string) => Stream = url => new EventSource(url)) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  patch = (next: Partial<WebRoomSessionState>) => {
    this.state = {...this.state, ...next};
    for (const listener of this.listeners) listener();
  };
  configure(identity: string, demoMode: boolean) {
    this.restoration = null;
    if (identity !== this.identity) {
      this.generation++;
      this.stopStream();
      this.identity = identity;
      this.loaded = false;
      this.loading = null;
      this.readers.clear();
      this.clearPreviews();
      this.state = initialState();
      this.patch({demoMode, authenticated: Boolean(identity)});
    } else if (this.state.demoMode !== demoMode) this.patch({demoMode});
  }
  private stopStream() {
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
  reconnect() { this.connect(); }
  private connect() {
    this.stopStream();
    const room = this.state.rooms.find(item => item.id === this.state.roomId);
    this.patch({connection: room?.enabled && this.identity ? "connecting" : "disconnected"});
    if (!room?.enabled || !this.identity) return;
    const scope = this.scope();
    const stream = this.createStream(this.api.eventsUrl(room.id));
    this.stream = stream;
    const valid = () => this.current(scope) && this.stream === stream;
    stream.addEventListener("snapshot", event => {
      if (!valid()) return;
      try {
        const next: WebSnapshot = JSON.parse((event as MessageEvent<string>).data);
        if (next.room_id !== room.id || !Array.isArray(next.messages) || !Array.isArray(next.outbox)) throw new Error("invalid_room_snapshot");
        const previous = this.state.snapshot;
        const ids = new Set(previous.messages.map(item => item.id));
        const added = previous.room_id === next.room_id ? next.messages.filter(item => !ids.has(item.id)).length : 0;
        const reading = [...this.readers.values()].some(Boolean);
        const pending = this.state.localSubmission;
        const acknowledged = pending && next.outbox.some(item => item.client_message_id === pending.payload.client_message_id);
        if (acknowledged) this.clearPreviews();
        this.patch({snapshot: next, connection: "connected", unread: reading ? 0 : this.state.unread + added,
          ...(acknowledged ? {localSubmission: null, text: "", reply: "", attachments: [], stickerResourceKey: ""} : {})});
      } catch {
        stream.close();
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
      this.patch({connection: "unavailable"});
    });
    stream.onerror = () => {
      if (!valid()) return;
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
