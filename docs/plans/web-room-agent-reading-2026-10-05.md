# Web Room Agent reading — accepted first version, 2026-10-05

Authority: the user requested a low-frequency HTML check → read new messages → decide → wait
workflow, and supplied Dots' four acceptance refinements. This implements that bounded first
version. Existing Web Room/Companion authentication, delivery and human unread behavior remain
authoritative. No new manual production deployment, enablement, external message, or merge is
implied; earlier merge approvals applied to delivered changes.

## Intended outcome and invariants

Agent processing progress is distinct from human viewing/unread. Focus, scroll, page reads and
opening Companion never advance it. One session shares presentation and transport ownership.
No new agent runtime, send automation, credentials, read-only CLI capability or dependencies.

The four user/Dots acceptance points map to:

- **A1 Fixed scope:** capture an immutable bounded message-ID/source-revision range. Complete
  only that server-owned batch cutoff; late arrivals/edits/deletes remain pending. Duplicate
  completion is idempotent and stale completion cannot advance a newer batch.
- **A2 Content changes:** new messages, same-ID edits/deletes and content loss count. Query all
  recorded current sources, including edits outside the normal 64-message view. Intermediate
  versions coalesce: this is not an event-replay archive. Presentation-only reactions/names
  follow existing source-version policy.
- **A3 Identity and durability:** progress persists by authenticated user + room + owned
  participant profile. Restart/profile/room/account transitions are isolated. Own echoes are
  excluded only using trusted delivered-source author_external_id, never a display-name match.
- **A4 Gaps:** unexpected disconnect, reload and unavailable/stale reads are unknown/need reread;
  reconnect cannot acknowledge them. New gaps during processing survive old completion.
  An orderly finite SSE rollover may avoid a gap only for its immediate healthy reopen.
  All batch copy states that only collected current sources are available. Discord Gateway
  and Connector loss cannot be reconstructed or certified by this change.

## Implementation contract

Accepted first version: full Web Room and Companion share an opt-in Agent reading panel, separate from human unread. Persist progress by authenticated user + room + owned participant profile. Uses existing latest RoomSourceRecord revisions (coalesced current state, not event replay), ALL recorded rows including old edits/deletes. No new transcript archive, agent runtime, dependency, send automation, auth principal, or tool-authority change.

API base /api/web-chat/rooms/{room_id}/agent-reading/{profile_id}
GET base => AgentReadingStatus
POST base/gap body {event_id: uuid-like string} => status (idempotent identical latest event_id)
POST base/batch body {} => status, containing existing active immutable reference batch or newly captured batch (limit64); no replacement until complete. Even empty batch allowed for explicit reread confirmation.
POST base/complete body {batch_id: string} => status. Complete strictly active server batch cutoff; never accept caller cutoff. Duplicate last completed batch ID idempotent; unrelated/stale IDs 409. Confirmation clears only the captured gap generation; a later reported gap remains sticky.

AgentReadingStatus {room_id, profile_id, cursor_revision:int, observed_revision:int, pending_count:int, needs_reread:bool, gap_generation:int, history_scope:'recorded_current_state', batch: AgentReadingBatch|null}
AgentReadingBatch {id:string, from_revision:int, to_revision:int, gap_generation:int, needs_reread:bool, items: AgentReadingItem[]}
AgentReadingItem {message_id:string, source_revision:int, room_revision:int, change:'new'|'edited'|'deleted'|'unavailable', state:'current'|'changed'|'removed', message:WebMessage|null}
Batch IDs + revisions only stored, no body text. Items compare captured revision to live current revision when rendered; changed/removed => message:null, explanatory placeholder. Source changing during batch is left pending by its newer room revision. Delete redacts old content. Same-ID source edits/deletes increment pending regardless latest ID unchanged.

RoomState row FOR UPDATE locks snapshot vs RoomRepository.observe; SQLite also shared RoomRepository._lock. Authentication/room access/fresh source permissions + WebProfileRecord.owner_id check inside transaction before every read/effect. Foreign-profile/foreign-room rejects, demo and CLI grants cannot write/read these routes. Own echoes filter ONLY author_external_id == profile_id from verified source provenance, never display name. Cap cutoff must not jump over omitted eligible entries. For needs_reread batch, include recent context as space allows in addition to pending; context must not let cutoff skip unselected pending. On a new cursor needs_reread true (gap_generation=1, completed_gap_generation=0).

Source gaps not intrinsically known: panel explicitly says collected current state only; unavailable/disconnect means unknown + needs reread, not zero/no change. On activation / reload and unexpected SSE errors frontend records gap event before fresh status, sticky local recovery until successful API. Only explicit batch+confirm clears recorded gap.

Snapshot adds source_revision integer for full room. Changes to old stored messages then cause existing SSE snapshot digest update. Server may emit `event: rollover\ndata: {}\n\n` on normal finite stream completion; frontend suppresses a gap only for next immediate normal reopen, delayed/failing reopen still marks gap. Keepalive heartbeat event can prove transport freshness (no second EventSource). Status auto-refresh on snapshot revisions/profile changes/connection recovery, never on scroll/focus or Dots polling; no busy loop or page reload.

UI proposed states unknown / needs_reread / processing / pending / idle. Visible concise HTML status with room+participant+observed revision+pending count+scope; stable data-agent-reading attributes, data-status, data-observed-revision. Toggle Agent reading; Read batch / Complete this batch; fixed batch from/to and readable bodies/media descriptions/deleted/changed placeholders. Disable complete while disconnected, status unknown, local gap unreported, demo or busy. Shared send composer unchanged. Low-frequency Dots read 60sec suggested configurable Dots side; tool-wait unverified, permission refusal not fixed/guaranteed.

## Delivery and proof

Backend/API tests must exercise A1–A4 and unauthorized room/profile/session access, bounded
backlogs, tombstone privacy and persistence. Frontend tests must cover scope-bound asynchronous
results, separate unread/processing state, gap generation and readable status/batch HTML.
An isolated actual API/database/Chromium journey must use real SSE and UI actions, not injected
snapshots, with synthetic messages only. Verify start, late arrival/edit/delete, confirmation,
reload and participant switching; preserve one EventSource and existing draft/send flow.

Run focused suites, frontend build/typecheck and proportional source checks. Apply bounded
mutations to fixed-cutoff, scope, source-revision and gap-clearing decisions, or record exact
unavailable evidence. Self-review and independent read-only review are distinct. Put implementation
receipts and the next gate only in PROJECT_STATE.md; architecture documents ownership.
Revert the feature code to retire the UI/routes; additive cursor metadata may be retained and
contains no copied message body. No destructive production cleanup is required.

Dots' actual low-frequency usage, tool element-wait capability, live send acceptance and
platform permission-refusal behavior are separate runtime qualifications, not promised fixes.
