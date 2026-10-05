# Web Room Agent reading

The opt-in Agent reading panel is available in the full Web Room and Room Companion.
It uses the current authenticated Web participant profile and the existing shared room
connection. Human unread counts continue to mean viewing, not completed Agent work.

## Dots operating loop

1. Open the granted room, choose the intended **Chat as** participant, and click
   **Enable Agent reading**. Initial activation and reload require a recovery reread.
2. At low frequency, read only visible HTML under **`[data-agent-summary]`**. This
   contains status, room/participant IDs, observed revision, pending change count and
   completed-through revision. Start with approximately 60 seconds between checks;
   the interval is an Agent-side operating preference, not a website timer or rate-limit
   guarantee. Read the rendered browser DOM; fetching the SPA index HTML does not contain live
   state. Do not refresh the browser or take a screenshot just to check this status.
3. For `pending` or `needs_reread`, click **Read batch**, then read the visible
   **`[data-agent-batch-id]`** section. Decide whether to reply using the normal composer.
   Reading, focus and scrolling do not complete a batch. Choosing no reply can still
   constitute completed processing.
4. Click **Complete this batch** only after deciding on its fixed range. Late arrivals,
   edits, deletes and newer recovery gaps remain for a subsequent round. Then wait.
5. If `processing` appears after reopening the panel, inspect the existing captured
   batch instead of trying to create another. If `needs_reread` appears alongside a
   captured batch, a newer recovery gap occurred; complete the original batch only
   after processing it, then read a recovery batch.
6. For `unknown`, pause message decisions. After connectivity returns, use **Retry
   status** if needed. A successful reconnect does not complete recovery work.

State attributes on `[data-agent-reading]` are `data-status`, `data-room-id`,
`data-profile-id`, `data-observed-revision`, `data-pending-count` and
`data-needs-reread`. Unknown numeric fields are the literal `unknown`, never a misleading
zero. Batch attributes are `data-agent-batch-id`, `data-from-revision` and
`data-to-revision`; items expose `data-agent-item-id`, `data-source-revision`,
`data-room-revision`, `data-change` and `data-item-state`.

## What progress means

Progress persists on the server separately for the authenticated account, published
room and owned participant profile. Switching rooms/profiles or reloading does not
transfer it to another participant. Enabling is session-only; re-enable after reload.
Own message echoes are filtered only by the verified delivered-source participant ID.
Another participant with the same name remains eligible.

The panel covers **collected current state**, including stored messages older than the
normal 64-message recent view. Message edits, deletion tombstones and content loss count
as changes even if the latest message ID is unchanged. Multiple intervening edits can
coalesce into one current source version; this is not a historical edit event journal.
Presentation-only names, avatars, pins and reaction counts follow the existing source
version policy and do not create processing work.

Each batch holds at most 64 immutable message/revision references and a server-selected
ending room revision. A changed/deleted captured source renders a placeholder rather
than substituting later content or resurrecting erased text. Changed live reply context
is likewise withheld. A following batch obtains the current change.

No message bodies are copied into processing storage. SQL queries bound source-body
reads and use a scoped aggregate for pending counts. Completion accepts only the active
server batch ID; callers cannot choose a cutoff. Duplicate last completion is harmless.
A recovery batch clears only the gap generation it captured; a later gap survives.

## Connection and coverage limits

The browser receives existing SSE updates autonomously. Source revision metadata also
notifies the panel about changes outside the recent view. Heartbeats establish current
transport activity; a bounded normal-rollover grace distinguishes the server's orderly
60-second stream renewal from an unexpected disconnect. Unexpected failure, stale
heartbeat, malformed state, failed reading calls and activation/reload require rereading.

Fresh access/transport does **not** prove complete Discord Gateway history. The current
Connector can miss observations during interruption or capacity failure; this feature
cannot retrieve unknown messages or certify upstream coverage. Recovery completion
means explicit review of the currently collected state only. The visible scope notice
retains this limitation even when no collected changes are pending.

HTML reads still pass through Dots' browser-tool authorization. This design reduces
repeated page work and duplicate context; it does not guarantee elimination of permission
refusals. Waiting on DOM changes has not been qualified and is not required by this release.

## Developer checks and rollback

No new package, secret or configuration toggle is needed. The additive table is
`web_room_agent_reading_cursors`, with the named `web-room-agent-reading-v1` schema
revision. Existing database initialization creates and records it idempotently.
Foreign keys cascade cursor metadata when account, room or profile is deleted.
Existing real-session, room-access, profile ownership, freshness, demo and restricted
CLI credential guards apply; this does not expand the read-only CLI's routes or grants.

Run:

```bash
.venv/bin/python -m pytest tests/test_agent_reading.py tests/test_web_rooms.py tests/test_agent_reading_postgres.py
npm run test --prefix web
npm run build --prefix web
.venv/bin/python scripts/verify_agent_reading.py --chromium /usr/bin/chromium
```

The PostgreSQL test runs only on the explicitly disposable `echo_masque_test` database
with the existing destructive-test opt-in; it is selected in PostgreSQL CI. Browser
acceptance starts an isolated real API/database, uses synthetic source ingress and real
SSE/UI actions, and makes no Discord webhook calls.

Disable Agent reading to stop the panel's processing workflow without changing normal
chat. Reverting the implementation retires routes/presentation; retained reference-only
cursor metadata does not require a destructive production rollback.
