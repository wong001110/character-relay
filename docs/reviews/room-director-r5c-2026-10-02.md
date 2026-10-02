# R5-C: Connector retirement and bounded room configuration

Base: `7c076c9f5dafef67940c5a5d94083b18bc58998b`. Self-review, not independent signoff.

Removed Connector semantic scoring/profile caches, old participation API, Roast/session execution,
expression candidate workflow retries, unique-role exclusion and recursive local bot continuation.
Ordinary messages use the Room Routing API; delivered social continuation retains backend bounds.
Expression selection is post-generation metadata matching; transport never retries a whole uncertain
answer or chooses an unrelated source. SDK source IDs and effective channel are checked on fetch.
Missing continuation evidence stops the optional continuation rather than silently retargeting.

The existing conversation-buffer configuration is still live: an authenticated, connection-scoped
`GET /api/connectors/discord/rooms/runtime` reads the existing runtime config. No legacy semantic
profile is fetched, and refresh failure preserves the last valid configuration. Ambient is off by
default; integers reject fractions and malformed values. Removed obsolete bypass observability.

## Evidence

Node 24.21.0: Connector typecheck/build and 152 tests in 23 files passed. Python 3.13.5:
29 focused routing, burst-observability and durability tests passed; whole-source mypy (339 files)
and Ruff passed. Five bounded manual mutations were killed by behavioral tests: missing source,
wrong source ID, wrong channel, fractional budget and missing configuration authentication.
No syntax error, timeout or infrastructure failure was counted as a killed behavioral mutant.
Files were restored and normal checks rerun. Exact logs are external execution evidence.

## Test disposition

Old Connector V3 profile/scoring/preflight and unique-role tests were retired with their removed
runtime. Replacements: `roomRoutingTransport.test.ts`, `roomEvidence.test.ts`, existing durable
runtime/turn-ingress/delivery tests, and `tests/test_room_routing_api.py`. Expression tests retain
rendering and custom-emoji stripping, not the deleted pre-generation semantic chooser. General
backpressure, expiry, shutdown, source/actor identity, scope and uncertain-delivery checks remain.

This is not R5 completion: Portal consumers/observations and R6 card/reset/fence integration remain.
No live Discord, model qualification, deployment, data deletion or full-final-head CI is claimed.
