# Web Room Agent reading — accepted session counter, 2026-10-05

Authority: after PR #227 was merged, the user explicitly replaced durable batch processing
with a frontend-only counter for messages received during the current participation session.
This revision supersedes A1–A4 batch/version/persistence/reread requirements. Implement and
prepare a reviewable PR; no new merge, manual deployment or production data purge authorized.

## Accepted behavior

- Opt-in Agent reading uses the existing shared WebRoomSession/EventSource in full room and
  native/fallback Companion. Enable/join starts at zero, treating current messages as context.
  Normal room and Companion views already open at latest; no historical batch is drained.
- Only previously unseen, live incoming message IDs increment the counter. Edits, deletions,
  reaction changes, repeat snapshots and verified own-participant echoes do not increment it.
  Do not identify own messages by display name. Verified participant identity comes from the
  existing trusted source delivery provenance: actor_type=web_participant and author_id=web:<profile_id>.
- Explicit Done/clear resets all currently counted reminders immediately in memory. A message
  observed after that click increments again. Scrolling/focus/human unread never clears it.
- Account, room or participant change, disable/re-enable, refresh and full document restart
  start a new counter. Route changes and Companion close/reopen share the existing session.
- Unexpected reconnect/offline establishes a fresh snapshot baseline; preserve already counted
  reminders but do not claim to count messages missed during the outage. Orderly SSE renewal
  retains its baseline. Disconnected/connecting/unavailable status remains visibly distinct from
  connected with zero reminders. No durable gap ledger or reread/processing-complete claim.
- Keep HTML [data-agent-summary], room/participant IDs, data-pending-count and explicit clear
  button readable to Dots. Low-frequency checking remains recommended; tool permission
  refusals and wait-on-element capability are outside this change.

## Retirement and boundaries

Remove active Agent reading API routes, request/status/batch schemas, repository, frontend API
client and batch UI. Retain the legacy cursor schema descriptor and initialization marker only
for database compatibility and existing owner-deletion cleanup; no reads/writes for counting.
Do not drop or purge existing rows/tables. Existing source collection, send receipts,
room/session authorization, Public Demo boundaries and CLI contracts remain unchanged.
No new dependencies, agent runtime, automatic send, backend counter or browser storage.

## Proof and delivery

Verify zero-on-join, live increments, clear/later-arrival, duplicate/edit/delete handling,
verified own echo, scope reset, shared presentations and disconnect/reconnect baseline.
Replace retired batch tests with API retirement/metadata preservation checks. Use a real
isolated API/database/Chromium journey, including actual SSE, Companion and offline/online.
Run relevant backend regressions, frontend suites/typecheck/build and proportional source
checks. Apply bounded scope/echo/reset mutations or document an unavailable proof gap.
Keep progress/results in PROJECT_STATE, ownership in architecture and Dots workflow in the
existing developer guide. Actual Dots acceptance remains separate from synthetic validation.
