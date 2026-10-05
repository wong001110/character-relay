# CLI read-only integration — accepted P0

Authority: the user supplied `Character_Relay_CLI_Integration_Handoff.txt` and on
2026-10-05 instructed implementation and merge to main. That instruction supersedes
the handoff's draft-only merge gate. Deployment, production migrations, real-account
approval/read and live messages remain outside this batch.

## Outcome and boundaries

A registered public `character-relay-cli` client requests a short-lived device grant.
The official `/cli/authorize` page requires an existing browser login, reviews explicit
room names/IDs, client, scopes, account and expiry, and requires Approve or Deny.
The grant remains separate from ordinary AuthSession/CurrentUser. Default-deny scoped
routes support identity, explicitly authorized room metadata and bounded messages only.
All writes and other session/connector/admin APIs reject CLI-shaped credentials even
when expired, revoked, malformed, owned by an admin, or legacy development auth is on.

Device authorization TTL is at most 600 seconds; access TTL at most 900 seconds.
No refresh token, offline access, message send, replay cursor, long-running daemon or
auto reply. State, polling penalties and one-use redemption are database-backed;
only hashes of private device/access credentials are persisted. Audit excludes
credentials, user/device codes and message content. Feature defaults disabled.

## Implementation contract

- Public POST `/api/cli-auth/device-authorizations`: JSON `client_id`, `scopes`
  (subset of `identity:read`, `rooms:read`, `messages:read`), nonempty explicit `room_ids`.
  Returns `device_code`, `user_code`, `verification_uri`, `expires_in`, `interval`.
- POST `/api/cli-auth/token`: OAuth form `client_id`, `device_code`,
  `grant_type=urn:ietf:params:oauth:grant-type:device_code`; standard pending,
  slow_down, denied, expired errors and one-time redemption. Responses no-store.
- Cookie-only GET `/api/cli-auth/browser-context`: `csrf_token`, `account`
  (`user_id`, `display_name`, `email`). POST `/api/cli-auth/authorizations/review`
  with `{user_code}` and POST `/api/cli-auth/authorizations/decision` with
  `{user_code, decision: approve|deny}` require same-origin plus `X-CSRF-Token`.
  Review returns `client_id`, `client_name`, `account`, `rooms: [{id,name}]`,
  `scopes`, `device_expires_at`, `access_token_ttl_seconds`.
  Review binds request to the reviewing account; another account cannot approve it.
- Cookie-only GET `/api/cli-auth/grants` returns `{grants: [...]}`; DELETE
  `/api/cli-auth/grants/{id}` requires CSRF and only revokes the logged-in user's grant.
  Grant metadata: `grant_id`, `client_id`, `client_name`, `scopes`, `room_ids`,
  `approved_at`, `expires_at`, `revoked_at`; no credentials.
- CLI Bearer GET `/api/cli-auth/me` returns user_id/display_name plus grant metadata.
  POST `/api/cli-auth/revoke` revokes only its own grant. GET `/api/cli/rooms`
  returns `{rooms: [{id,name}]}`; GET `/api/cli/rooms/{id}/messages` and `/events`
  return recent at most 64 messages, using existing Web Room access/freshness checks.
  SSE is snapshot change notification, not durable replay; revalidation each second
  and before emission, plus a 5-second processing timeout, bounds invalidation to
  6 seconds under responsive event-loop scheduling. Timed-out worker output is discarded.
- Separate `character-relay-cli` console client uses the fixed official HTTPS origin,
  verified TLS and no redirects. Same-process approval polling, identity and specified
  room reads, optional revoke; token is only in RAM. No Cookie, password, refresh,
  credential file, arbitrary target or mock-to-real switch.

## Acceptance and evidence

Synthetic tests must prove state/polling/expiry/CSRF/account binding, scope and room
limits, admin/write refusal, DB restart and concurrent single redemption, SSE
revocation/expiry/account/membership invalidation, absence of secret output, and
existing authentication/Web Room compatibility. Bounded semantic mutations cover
protected decisions. An isolated real API + Chromium journey must exercise review,
explicit approval and grant revocation. CI must pass the exact PR head before the
authorized squash merge. Documentation includes API/client use, additive schema and
safe rollback. Production and Dots runtime validation remain explicitly unrun.
