# Short-lived read-only CLI access (P0)

Registered public client: `character-relay-cli` (**Character Relay CLI**), with no
client secret. CLI grants are separate from login sessions/admin privileges. They
do not change Dots execution-platform permission gates or authorize auto replies.

## Enablement and client

The service defaults to disabled (`CHARACTER_RELAY_CLI_AUTH_ENABLED=false`). After
separately authorized deployment, enable it and verify
`CHARACTER_RELAY_CLI_AUTH_PUBLIC_ORIGIN` (default
`https://echo-masque-production.up.railway.app`). This must be credential-free HTTPS
with no path/query, never a client-supplied Host header. Device/access TTL settings
`CHARACTER_RELAY_CLI_DEVICE_TTL_SECONDS` / `CHARACTER_RELAY_CLI_ACCESS_TTL_SECONDS`
default to 600/900 and permit only 1–600 / 1–900 seconds respectively.

Install the existing Python package, then run in **one process**:

```bash
character-relay-cli --room EXPLICIT_RELAY_ROOM_ID --revoke
# Equivalent before reinstalling the package:
python -m echo_masque.cli_client --room EXPLICIT_RELAY_ROOM_ID --revoke
```

Repeat `--room` for up to 32 explicit Web Room IDs (not Discord channel IDs or a
wildcard). Open the displayed official URL, log in normally, enter the displayed
code, review account/client/rooms/read operations/expiry, and explicitly Approve
or Deny. Opening a link never approves. Review binds the request to this account;
changing account requires a new request. The client checks identity/room metadata,
reads each bounded snapshot and displays counts, without transcript or raw responses.
`--revoke` revokes its current grant; otherwise it expires within 15 minutes of
approval and can be revoked in Account settings.

Only URL, human code, status, minimal non-secret identity and counts are printed.
Private device/access credentials live in local variables only. No Cookie/password,
credential file, environment credential, refresh token, daemon, redirect, arbitrary
target or mock-to-real switch. TLS verification is mandatory. Pending, slow_down
and connection timeout handling reduce polling frequency and have a finite deadline.

## HTTP contract

`/openapi.json` contains request/response schemas, restricted Bearer metadata and
OAuth form fields. JSON is used on device/browser routes; token uses UTF-8 OAuth
form. Never put device/access credentials in URLs, command arguments, logs or files.
Responses/OAuth failures use no-store; input-validation errors never echo input.

| Request | Authentication, input and result |
| --- | --- |
| POST `/api/cli-auth/device-authorizations` | Public client; JSON `{client_id, scopes, room_ids}`. Returns private `device_code`, displayed `user_code`, `verification_uri`, `expires_in`, `interval` (initially 5 seconds). |
| POST `/api/cli-auth/token` | Form `client_id`, private `device_code`, `grant_type=urn:ietf:params:oauth:grant-type:device_code`. Returns private `access_token`, `token_type: Bearer`, `expires_in`, space-separated `scope`; no refresh. |
| GET `/api/cli-auth/browser-context` | Real active browser session Cookie; `{csrf_token, account: {user_id, display_name, email}}`. CSRF stays in memory. |
| POST `/api/cli-auth/authorizations/review` | Cookie + same official Origin + `X-CSRF-Token`; `{user_code}`. Returns server-owned client name/ID, account, rooms `{id,name}`, scopes, `device_expires_at`, `access_token_ttl_seconds`. |
| POST `/api/cli-auth/authorizations/decision` | Same browser/CSRF, review required; `{user_code, decision: approve\|deny}`. Returns status and grant metadata (null when denied). |
| GET `/api/cli-auth/grants` | Cookie, own most recent 100 grants, including expired/revoked metadata; `{grants: [...]}`. |
| DELETE `/api/cli-auth/grants/{grant_id}` | Cookie + Origin/CSRF, owner only, 204. |
| GET `/api/cli-auth/me` | CLI Bearer + `identity:read`; minimal identity plus grant metadata. |
| GET `/api/cli/rooms` | CLI Bearer + `rooms:read`; only granted `{rooms: [{id,name}]}`. |
| GET `/api/cli/rooms/{room_id}/messages` | CLI Bearer + `messages:read` and explicit room, bounded snapshot. |
| GET `/api/cli/rooms/{room_id}/events` | Same scope, finite SSE snapshot change notifications. |
| POST `/api/cli-auth/revoke` | CLI Bearer, only its own grant, 204; works after room-access loss while account/token remain active. |

Scopes are only `identity:read`, `rooms:read`, `messages:read`; nonempty room IDs are
mandatory even for identity-only scope. Unsupported clients/scopes, wildcards, extra
fields and ambiguous forms fail closed. No write/admin/session/connector inheritance.
Every selected room is checked at approval, redemption and each read against existing
active-account, server access, room membership and fresh connector permission evidence.
Losing one selected room denies the entire grant's reads, including otherwise permitted
rooms. A CLI-owned admin role gives no extra permission. Browser-only routes reject
Bearer authentication; CLI-only routes reject session Cookies as CLI credentials.

Metadata fields: `grant_id`, `client_id`, `client_name`, `scopes`, `room_ids`,
`approved_at`, `expires_at`, `revoked_at`; identity adds `user_id`, `display_name`.
CLI reads contain no email, role, password, Cookie, session ID or credential.

Fixed OAuth 400 error names: `authorization_pending`, `slow_down` (+5 seconds to
the persisted interval on each early poll), `access_denied`, `expired_token`,
`invalid_grant` (also repeat redemption), `invalid_client`, `invalid_request`,
`unsupported_grant_type`. Read errors include 401 invalid token; 403 insufficient
scope, room not granted or restricted credential; 404 disabled/unavailable room;
409 already decided; 422 invalid JSON; 429 rate/capacity; 503 stale permissions.
Browser errors include login-required, CSRF rejection and account mismatch.

## Snapshot and SSE

Snapshot: `{room_id, history_limit: 64, messages: [...]}` with no outbox. Message
fields retain Web Room presentation: `id`, `author_id`, `display_name`, `avatar_url`,
`actor_type`, `text`, `deleted`, `content_available`, `created_at`, `edited_at`,
`reply_to_message_id`, `reply_preview`, `attachments`, `custom_emojis`, `stickers`,
`mentions`, `embeds`, `poll`, `reactions`, `pinned`. Reply previews are bounded
summaries in the same room. Rich media is metadata/URLs, not privileged download.

SSE emits `snapshot` (JSON above), `revoked` (fixed authorization-unavailable reason),
`unavailable` (fixed processing-failure reason), and keepalives. SHA IDs are change
fingerprints, **not replay cursors**; no Last-Event-ID/after_cursor, retention or
missing-message recovery. Connections last at most 60 seconds. Revalidation occurs
before/after snapshot I/O and after serialization before emission. Polling is every
1 second and processing has a 5-second timeout: **6-second invalidation bound under
responsive event-loop scheduling**. A stalled worker thread may finish later but
cannot emit after the generator closes. Per-worker caps: 3 streams/user, 128 total;
70-second leases recover abandoned admission. Distributed grant state remains in DB.

Persistent rate buckets: device admission 20/IP/minute and 1000/minute globally;
review/decision 20/account/minute; token 120/IP/minute; reads use the configured
per-account request limit. Proxy-shared IPs share caps. Human codes carry about
50 bits of entropy; only their hashes are stored.

## Schema and safe rollback

Bootstrap adds `cli_device_authorizations` and `cli_readonly_grants` and records
`cli-readonly-grants-v1` under the existing SQLite/PostgreSQL initialization lock.
No existing session/room/message row is rewritten or purged. Only SHA-256 hashes
of device/user codes and tokens are stored. Poll version/interval, account binding,
decisions, revocation and one-time redemption survive restarts and multiple workers.
Audit stores actor, action, resource ID and client ID only, never credentials/codes,
Cookies or message bodies.

Disable the feature before rolling back code. Requests and established streams fail
closed when disabled. Retain additive tables, revision and audit; no destructive
downgrade is needed. Expired requests/grants are retained in P0; archival/retention
is a separate change. Production migration, enablement and real-account approval/read
were **not run** in this batch.

## Verification and limits

```bash
python -m pytest tests/test_cli_auth.py tests/test_cli_client.py tests/test_cli_auth_postgres.py
npm run build --prefix web
python scripts/verify_cli_readonly.py --chromium /usr/bin/chromium
```

The browser harness uses real isolated API/database/Chromium login, review, approval,
revoke, the real client through a loopback-only transport, and real HTTP SSE closing
after revoke. No mocked responses, deployed service, real account or message send.
The PostgreSQL suite requires the existing explicit opt-in to disposable
`echo_masque_test` and is selected in CI. Exact receipts and bounded mutation scope
are in `PROJECT_STATE.md`. Dots runtime acceptance, production enablement, sending,
refresh/offline access, durable replay and persistent credential storage remain
unimplemented/unrun. The referenced mock ZIP was not supplied and is not used.
