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

### 3. Accepted send can leave the composer blocked

The browser keeps a separate local submission until the SSE snapshot contains the same client
message ID. If the POST has already returned 202 but that SSE update is delayed or missed, the
composer remains disabled and later clicks appear to do nothing.

Required direction:
- treat the successful POST receipt as the acknowledgement boundary and surface it locally at once;
- keep SSE as convergence with server state rather than a prerequisite for re-enabling the composer;
- bound the POST wait so a stalled request becomes an explicit unknown result with the existing
  idempotent safe-retry path instead of leaving the UI blocked indefinitely;
- do not resend automatically after an unknown network effect.

### 4. Discord reaction changes can miss Web Room

The accepted optimization requires the Connector to re-fetch the exact Discord message after every
reaction event. The current handler only re-fetches partial messages and otherwise trusts the cached
Message object, so a Discord reaction can remain absent from the Web Room snapshot.

Required direction:
- force-fetch the exact message for add/remove/remove-all/remove-emoji reaction events before
  publishing Room evidence;
- publish aggregate Discord counts as presentation-only state;
- preserve the existing distinction that Web-profile reactions are Web identities and do not
  silently impersonate native Discord reactions.

### 5. Web Room general attachments

The user explicitly expanded the earlier image-only scope to Discord-style file attachments.

Accepted bounded scope:
- select or drag up to 4 attachments per message, maximum 8 MiB each;
- paste clipboard files when the browser exposes them;
- support validated images plus common text, PDF, Office, archive, audio and video formats;
- do not accept arbitrary executable/script formats merely because the browser supplies a MIME type;
- validate image bytes server-side; for other files require an allowed filename extension plus a compatible declared MIME type;
- keep uploaded bytes private and short-lived in the existing generated-media artifact store;
- bind Connector download to the exact room outbox claim; do not expose a public upload URL;
- deliver all attachments through the existing Discord Webhook `files` transaction;
- retain local thumbnail previews for images; render non-image uploads as attachment chips/cards;
- remove private temporary bytes when delivery becomes terminal; abandoned uploads remain TTL-bounded and opportunistically purged;
- attachment resources remain structured media evidence and are never appended to LLM prose as temporary URLs/base64.


## Already fixed and to regression-check

- historical malformed Discord tombstones no longer break SSE/reactions;
- same-room reconnect keeps the transcript mounted;
- manual Refresh rooms does not restart the active EventSource;
- `/rooms?room=...` direct browser refresh reaches the Portal instead of FastAPI 404.

## Follow-up policy

Accumulate additional real-use findings here first. Prefer fixing shared state-model causes over
isolated UI patches. Do not expand into unrelated Discord parity features during this pass.

