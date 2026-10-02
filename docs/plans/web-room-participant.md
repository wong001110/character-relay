# Web Room Participant

Accepted for implementation and combined squash merge with PR #209 on 2026-10-02.
Progress belongs only in PROJECT_STATE.md. This extends the group-chat refactor; it does
not reinstate retired semantic, relationship, or autonomous activity machinery.

## Bounded product scope

An existing authenticated website account can open explicitly permitted Discord rooms,
see bounded message history plus real-time creates/edits/deletes, select an owned participant
profile (display name/avatar), send a text message, and reply to a visible message. The
Discord connector sends as an application-owned webhook. No Discord user/self-bot login,
new model runtime, typing/presence, attachments, reactions or voice is required here.

The connection owner must deliberately publish a room to the website and grant individual
account access. The bot being able to see a channel is not permission for every website
account to see it. Default is no membership. Revocation applies to history, live streams,
queued sends and delivery. Native private Threads remain separately scoped.

Profiles have stable IDs tied to the authenticated account. Display names and avatars are
presentation only, never another character/human identity or a grant to execute tools.
Browser requests never contain a Discord webhook token. Use the current server-side SDK and
credential store. Content and user-selected avatar URLs remain untrusted.

## Transport and durable behavior

Use same-origin authenticated SSE for receiving and REST for sending. Database-backed
bounded snapshots/cursors support reconnect and multiple API workers without another broker.
A connected page is not proof that an external agent will autonomously remain active.

A send has an account-bound idempotency key and durable pending/claimed/delivered/failed/
uncertain state. Only a Discord acknowledgement is a confirmed delivery. A timeout after
starting an external send must not automatically retry. Reconcile Gateway echoes by actual
Discord message ID; a gateway event and its receipt must not render two messages or run two
character turns. The sender's webpage and other participants see the same committed message.
Reply targets must be visible in that exact room; a webhook may use a safe source link and
stored ancestry rather than pretend to support a native Discord Reply API.

## Acceptance

- Existing login opens the room page; unauthenticated and non-member access is denied.
- A profile belonging to another account cannot be selected, altered, or impersonated.
- Name/avatar changes do not affect account, room, character or tool permissions.
- Discord create/edit/delete updates the room. Initial history and reconnect stay bounded.
- Revoked membership/session/Discord read permission closes or blocks further reads/sends.
- Duplicate POST and reconnect do not duplicate delivery; pending is not displayed as sent.
- Discord rate error, definitely-unsent, receipt failure and timeout are distinguished.
- Gateway-before-receipt and receipt-before-Gateway each produce one canonical message.
- Replies cannot reference another room, deleted source or unreadable Thread.
- Explicit allowed_mentions prevents everyone/role pings; no token reaches the browser/log.
- User-facing errors and connection state are available to keyboard and screen-reader users.
- Backend/Connector contract tests and a real local browser-to-API journey are verified.
- Public Demo remains server-enforced read-only. Live Discord/model acceptance is user-owned.

## Reuse references, checked 2026-10-02

- Discord Execute Webhook: https://docs.discord.com/developers/resources/webhook
  Use the existing discord.js client, explicit wait-for-message acknowledgement and bounded
  allowed mentions; username/avatar override does not create a Discord user.
- Discord Gateway events: https://docs.discord.com/developers/events/gateway-events
  Reuse existing create/edit/delete ingress and permission-aware Reply ancestry.
- Character Card V2: https://github.com/malfoyslastname/character-card-spec-v2
  Reference for portable authored fields; never import credential/tool authority.

No external implementation is copied verbatim and no new service is introduced.
