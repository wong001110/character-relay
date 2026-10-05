# Web Room Agent reading: session reminders

The user replaced durable processing batches with a frontend counter after PR #227.
Full Web Room and native/fallback Room Companion share the current Portal session,
existing SSE and draft. Human unread remains separate.

## Dots operating loop

1. Enter a room, select your participant and enable Agent reading. The current recent
   messages are context; reminders start at 0. Companion shows the latest five messages.
2. At low frequency (for example every 60 seconds), read `[data-agent-summary]`. It exposes
   room/participant IDs, connection state and the current session's new-message count.
3. If connected with a nonzero count, read the normal latest room/Companion messages,
   decide whether to reply and use the existing composer if appropriate.
4. Click **Done · clear reminders** (`[data-agent-clear]`) when finished. All currently
   counted reminders clear immediately. A later observed incoming message increments again.
5. Wait for the next low-frequency check. No automatic reply, page reload or tool invocation.

The panel exposes `[data-agent-reading]`, `data-room-id`, `data-profile-id`,
`data-status=disabled|disconnected|pending|idle`, numeric `data-pending-count` and
`data-connection`. A disconnected zero is not proof that no messages arrived.

## Session boundaries

Enable/join starts at zero. Refresh, document restart, account/room/participant change or
disable/re-enable starts again. Route changes and Companion close/reopen preserve the shared
session counter. Scrolling, focus and human unread acknowledgements never clear it.
Only new live IDs count. Edits/deletions/reactions do not count; verified own profile echoes
are excluded using the existing canonical author identity, never a display-name match.
Deduplication retains at most512 message IDs for the latest-64 snapshot transport; it stores
no extra bodies. Reappearance after that bounded window is not durable-history tracking.

Unexpected stream loss/offline/manual reconnect establishes a new baseline from the next
snapshot. Already counted reminders remain until clear; messages missed during an outage
are not guaranteed to count. Normal immediate finite SSE renewal retains its baseline.
Visible connection status and the heartbeat watchdog remain. Dots element-wait capability
and browser-tool permission stability are not verified or guaranteed.

## Backend retirement and rollback

The previous `/api/web-chat/rooms/{room}/agent-reading/{profile}` status/gap/batch/complete
routes, schemas, repository and frontend client are removed. UI counting sends no processing
API requests and persists no progress. Normal authenticated room/message/send APIs remain.
Legacy `web_room_agent_reading_cursors` metadata and `web-room-agent-reading-v1` initialization
are retained for database compatibility and owner-deletion cleanup only. Fresh bootstrap may
create the empty compatibility table; it never receives new reading progress. Existing
records are not purged or dropped. Reverting this change restores the previous feature;
there is no destructive downgrade or manual production operation in this delivery.

Reproduce synthetic acceptance after building the Portal:

```bash
.venv/bin/python scripts/verify_agent_reading.py --chromium /usr/bin/chromium
```

This uses an isolated actual API/database, Chromium, synthetic sources/delivery receipts
and native SSE/Companion. It does not send a Discord webhook or contact deployed services.
Actual Dots cloud-browser acceptance remains a separate qualification.
