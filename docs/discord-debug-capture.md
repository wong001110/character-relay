# Discord temporary debug capture

Status: **Phase 1 operational and privacy contract**

Character Relay keeps ordinary Discord Connector events structured and free of message bodies. When a production problem cannot be diagnosed from identifiers, reason codes, counts, and timings, the Bootstrap Admin may temporarily enable a narrowly scoped Runtime-ingress capture for one Discord Server.

This is Option B. It is a short-lived debugging exception, not a normal log mode and not a complete Discord Gateway packet capture.

## What it captures

The capture observes validated `DiscordInboundMessage` data only when it reaches a real Character-generation step. This includes direct `/api/connectors/discord/messages` turns, non-durable Social Turn steps, and newly generated durable Social Turn steps. A durable replay returns the stored result and is not captured again. Delivery claim/acknowledgement calls are also outside the capture point.

The payload can include the triggering text, recent messages supplied to the Character, member and message identifiers, attachment/link-preview metadata, and other normalized fields used by the Character turn.

It does not capture Discord events discarded by the Connector before Runtime submission. It also does not capture the Connector shared secret, Bot token, provider key, request authorization header, or the Discord Gateway's original JSON envelope.

## Privacy and storage boundary

- Capture is off by default.
- Only the configured Bootstrap Admin/Super Admin can start, stop, list, reveal, or clear a capture.
- One capture is scoped to one stored Server Profile's Discord Connection and Guild.
- Raw payloads remain only in bounded application-process memory. They are not written to SQLite, WAL, backups, account exports, ordinary Connector events, Provider Trace, docs, or OpenWiki.
- Restarting or redeploying the application clears active sessions and captured payloads.
- Capture, outcome-marking, pruning, and viewing failures must not change the Character Turn response or error semantics.
- Start, stop, raw-detail reveal, and clear actions are audited using identifiers/counts only. Audit metadata never contains captured text.

This memory-only design matches the currently supported single-replica topology. It is not a durable multi-replica debug system.

## Bounds

The Bootstrap Admin chooses one of these expiry periods:

- 15 minutes
- 1 hour
- 24 hours

Only one active session is allowed for a Server. A session holds at most 100 records and 10 MiB; the whole process holds at most 500 records and 50 MiB across Servers. When a record-capacity limit is reached, the globally oldest applicable record is evicted and its session reports the eviction count. Expired sessions automatically lose their raw records. Stopped-session records remain available for explicit review/clear until expiry, a replacement session starts for that Server, or the process restarts.

The process retains at most 500 session summaries. Expired summaries are the only summaries evicted to admit a new Server scope; if all 500 summaries are still active or within their stopped-retention period, starting another capture is rejected instead of deleting retained raw records early.

Repeated delivery of the same Runtime message within a session is deduplicated by scoped operation/message identity. This protects the debug view from transport retries; it is not a replacement for Runtime side-effect idempotency.

## Portal workflow

```text
Behavior Notebook
→ select a Discord Server
→ Temporary Runtime ingress capture
→ choose 15 minutes / 1 hour / 24 hours
→ Start capture
```

The record list shows summaries only. Raw content is fetched only after an explicit reveal action, is returned with `Cache-Control: no-store`, and is never auto-refreshed into the page. Stop capture when reproduction is complete and clear the records after collecting the minimum diagnostic evidence needed.

Do not copy raw captures into issue trackers, screenshots, docs, chat, test fixtures, or OpenWiki. Prefer recording the structured reason, identifiers, and a redacted explanation of the failure.

## Ordinary Discord events

Ordinary Connector events may contain operational summaries, IDs, reason codes, booleans, counts, scores, timing, and selection metadata. They must not contain `trigger_preview`, message `text`, prompts, responses, payload dumps, planning text, or other nested content-bearing fields.

Connector process logs and heartbeat metadata reduce exceptions to an allowlisted error kind/code and numeric HTTP status. They do not copy exception messages, response bodies, causes, stacks, or arbitrary error metadata.

Message-body fingerprints are deliberately omitted: short messages can be recoverable through dictionary comparison. Use the Discord source message ID to correlate an ordinary event with an active temporary capture.

## Option C extension boundary

The Runtime capture caller depends on a payload codec and capture-store interface. A future Option C may implement a dedicated encrypted archive, separate encryption key, durable retention policy, and multi-replica coordination behind those interfaces. Option C requires its own security/storage review; it must not silently change Option B into SQLite persistence or reuse the Credential Vault's credential lifecycle.
