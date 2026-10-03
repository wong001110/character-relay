# Web Room follow-up — 2026-10-03

Working branch: `fix/web-room-followup-20261003`

Do not merge to `main` until the user explicitly closes the current follow-up pass.

## Confirmed unresolved items

### 1. Stale delivered receipts reappearing

Current UI reconciliation compares recent Web outbox receipts only against the bounded recent Room
snapshot. A previously delivered Web message can reappear later when its Discord message falls out of
the 64-message Room window while the outbox receipt is still among the latest 32 receipts.

Required direction:
- treat delivery receipt state as a finite UI lifecycle, not as chat history;
- once a delivered receipt has been reconciled to its Discord message, it must stay retired from the
  conversation UI even after that Discord message falls outside the current history window;
- do not “fix” this by merely increasing the history limit;
- pending / claimed / failed / uncertain states remain visible as appropriate;
- preserve durable delivery/retry/idempotency semantics for the Connector and Character Agent path.

### 2. Web -> Discord reply semantics

Current Web Room reply delivery prepends a Discord message URL to message content. Discord renders
that as a channel/message jump link rather than a native Reply preview.

Required direction:
- use a native Discord message reference when the webhook/Discord API path supports it;
- if native webhook reply is unavailable, use an explicit readable fallback with referenced author
  and bounded source summary instead of a bare Discord URL;
- keep `reply_to_message_id` as structured RoomSource evidence for Character Agent group-chat
  context;
- never make a presentation fallback URL part of Agent conversational prose.

## Already fixed and to regression-check

- historical malformed Discord tombstones no longer break SSE/reactions;
- same-room reconnect keeps the transcript mounted;
- manual Refresh rooms does not restart the active EventSource;
- `/rooms?room=...` direct browser refresh reaches the Portal instead of FastAPI 404.

## Follow-up policy

Accumulate additional real-use findings here first. Prefer fixing shared state-model causes over
isolated UI patches. Do not expand into unrelated Discord parity features during this pass.
