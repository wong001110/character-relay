# Connector retirement and Web transport checkpoint

Source parent: `43faee6957734cff62712522fec6d6c9ba347846`. Current progress is only in
PROJECT_STATE.md. This review does not declare R5/R6 or release acceptance complete.

## Changed boundaries

- Discord keeps Gateway ingestion, exact channel/native Thread checks, webhook execution and
  receipt recovery. Python keeps account/server/room membership, profile ownership, scoped
  source attribution, budgets and delivery state. The browser never receives webhook secrets.
- A published room needs a connection custodian; another account needs both server access and
  an explicit room membership. Login or a profile named “Admin” grants nothing. Room pause,
  session/member revocation and unreadable/stale source checks stop reads/new sends.
- Each Web request has an account-bound idempotency key. The payload/display identity is captured
  at enqueue. Claim expiry is uncertain, not resendable. Only an exact matching webhook receipt
  confirms delivery. ACK repair retries persistence, never Execute Webhook. Partial ambiguity
  cannot fall back to a different transport or random speaker.
- Gateway may precede the send receipt. Unbound application Web webhook messages wait for the
  durable mapping, then become stable `web:<profile>` actors. Source delete tombstones stay sticky.
  Another room, another webhook or model-supplied external identity cannot adopt that mapping.
- External participant direct routing does not create a human requester/grant. Ordinary other
  bots remain untrusted; unaddressed external-agent messages do not force a Character response.
- SSE uses bounded database-backed snapshots, periodic session/membership/source permission checks
  and expiring per-worker stream leases. It needs no message broker; reconnect replaces the view.
  Per-worker stream limits are not represented as distributed quotas.

## Evidence and limits

43 Python integration cases; 149 Connector cases; 64 Portal cases passed at this checkpoint.
Python/TS typing, Ruff and Portal build passed. Some previous tests exclusively asserting deleted
legacy policy were retired; source/permission/claim/partial-send negative tests remain. New tests
cover missing grants, foreign profile, unsafe avatar syntax, payload-key conflict, unknown receipt,
wrong claim/webhook, sticky deletion and no duplicate send during ACK failures.

Local Playwright navigation is host-policy blocked. Browser-to-real-API/SSE, complete PostgreSQL,
new-table lifecycle, integrated mutation and release tests remain closeout work. Synthetic transport
results are not human/model quality evidence. HTTPS avatar syntax is validated without fetching;
external image hosts can observe browser requests. No live credentials/captures appear in tests.
