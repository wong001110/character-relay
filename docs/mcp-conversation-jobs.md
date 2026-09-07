# MCP tools and asynchronous conversation turns

Status: implemented on `codex/ai-native-reliability-review`, Draft PR #204; not deployed.
This contract covers controlled MCP discovery/invocation and progress/result delivery for slow
Discord turns. Knowledge Fabric sync remains the responsibility of its dedicated worker.

## Conversation behavior

When a Character needs a slow tool, its model supplies a short `progress_message` in the
Character's voice and the conversation's language. After admission, Runtime publishes that
message before executing the slow operation. The Connector can deliver it while generation
continues. For example: “我先去生成圖片，完成後貼給你。” This is model-authored text, not a
hardcoded opening on every conversation. A job permits at most three progress messages of
500 characters each. Progress neither advances a social cursor nor starts a bot-tag chain.

The completed tool result returns to the same Character turn. Native generated images and
supported MCP inline images use the existing owner-scoped artifact store and original Discord
destination/identity. The model receives artifact references and delivery status, not image
base64, and writes the final response without uploading the same image again. Image and final
text are separate deliveries; this is not an atomic image-plus-text transaction.

Normal per-destination conversation ordering remains serial. Slow work no longer requires one
long HTTP request, but it still holds that destination's current turn. Allowing later messages
to overtake it requires a separate context/cancellation contract.

## MCP capability and authority

Operators configure exact HTTPS Streamable HTTP endpoints. A deployment needs both a manual
tool assignment and an explicit operator grant for its owner/deployment pair and remote tool
names. An MCP server cannot grant itself access by returning a descriptor or annotation.

1. An assigned `mcp.discover` remains available when ordinary tool relevance pruning finds no
   match. Initially `mcp.invoke` is withheld from the model's tool list.
2. Discovery ranks granted tools from configured providers and returns at most three complete
   descriptors within a bounded aggregate response. Oversized or unsupported schemas are
   omitted with a reason; schemas are not truncated into invalid JSON.
3. Successful discovery makes an assigned `mcp.invoke` available. Invocation refetches the
   catalog, compares its fingerprint, validates arguments, and rechecks current deployment/tool
   authorization before the remote call. Revoked image-delivery authority is checked again
   after generation and before posting the artifact.
4. Remote descriptions/results are untrusted tool data. Invocation conservatively counts as a
   side effect even if the remote server claims it is read-only. An unknown/failed invocation
   consumes the turn's write budget and is not automatically repeated.

Discovery searches **connected, authorized providers**, not an Internet-wide tool marketplace.
There is no automatic MCP installation, executable stdio command, OAuth authorization flow,
legacy SSE endpoint, or arbitrary resource-link fetch. A missing grant/provider/tool remains
an explicit missing capability.

## Configuration

The default `CHARACTER_RELAY_MCP_PROVIDERS=[]` makes no MCP connections. Configure the API
process with JSON, replacing placeholder identities and tool names with actual assigned values:

```json
[
  {
    "id": "art-tools",
    "endpoint": "https://mcp.example.com/mcp",
    "bearer_token_env": "CHARACTER_RELAY_ART_MCP_TOKEN",
    "deployment_grants": [
      {
        "owner_id": "owner-id",
        "deployment_id": "deployment-id",
        "tool_names": ["generate_image"]
      }
    ]
  }
]
```

Set that JSON as `CHARACTER_RELAY_MCP_PROVIDERS`. Inject the actual token separately into the
API process environment under `CHARACTER_RELAY_ART_MCP_TOKEN`; the JSON contains only its
environment-variable name. Omit `bearer_token_env` for an endpoint that needs no bearer token.
After API restart, manually assign `mcp.discover` and `mcp.invoke` in Deployment Center to the
intended deployment. Existing native `image.generate` assignment remains independently usable.

| Setting | Default | Supported bounds / meaning |
| --- | --- | --- |
| `CHARACTER_RELAY_TURN_JOB_MAX_QUEUE` | 20 | 1–200 waiting jobs per API process |
| `CHARACTER_RELAY_TURN_JOB_MAX_CONCURRENCY` | 2 | 1–16 executing jobs per API process |
| `CHARACTER_RELAY_TURN_JOB_DEADLINE_SECONDS` | 300 | 30–900 seconds, including queue wait |
| `CHARACTER_RELAY_TURN_JOB_RETENTION_HOURS` | 24 | 1–168 hours for job/progress records |
| `DISCORD_TURN_JOB_MAX_WAIT_MS` | 330000 | Connector overall wait; align above API deadline |
| `DISCORD_TURN_JOB_RECOVERY_MAX_CONCURRENT` | 4 | 1–10 recovery jobs; bounded pending queue |
| `DISCORD_TURN_INGRESS_MAX_PENDING` | 100 | 1–1000 Connector preflight, collected-burst, and runtime tasks per process |
| `DISCORD_TURN_INGRESS_MAX_PENDING_PER_DESTINATION` | 8 | 1–100 pending tasks for one channel/thread destination |
| `DISCORD_TURN_INGRESS_MAX_PREFLIGHT_AGE_MS` | 30000 | 1000–300000; stale work is rejected before Runtime/API submission |
| Provider `list_timeout_seconds` | 10 | 1–10 seconds |
| Provider `call_timeout_seconds` | 90 | 1–120 seconds; also bounded by overall job deadline |
| Provider `catalog_ttl_seconds` | 300 | 60–3600 seconds; invocation refreshes regardless |
| Provider `max_catalog_pages` / `max_catalog_tools` | 10 / 100 | At most 20 / 200 |
| Provider `max_http_response_bytes` | 12000000 | Stream bytes are bounded before SDK parsing |
| Provider `max_image_bytes` | 8388608 | At most one inline image; PNG/JPEG/WebP/GIF, verified |

Endpoints must use public HTTPS on port 443 with no credentials, query string, or fragment.
Redirects, environment proxies, and compressed responses are rejected. The client uses the
official MCP Python SDK 2.x Streamable HTTP transport; tests exercise JSON and SSE responses
in-process. JSON-schema validation intentionally accepts a restricted, bounded subset; regex,
references, and combinators are excluded. This can make some real server tools unavailable.
Public-address validation is not DNS-to-connection binding; network-level egress restrictions
remain an operator concern and a recorded project follow-up.

## Job lifecycle and delivery

The API lifespan owns a bounded in-process execution queue backed by durable job/result records.
This is not a distributed queue or a separately deployed worker. Multiple API replicas have
separate admission limits. A request is validated for current owner, connection, deployment,
guild, channel, thread, and category before acceptance or reattachment.

| Connector endpoint under `/api/connectors/discord` | Contract |
| --- | --- |
| `POST /messages/jobs` or `/social-turns/jobs` | Accept/reattach a deterministic source-event job; return 202 |
| `GET /turn-jobs/{job_id}?connection_id=…` | Scoped progress, terminal status, and stored reply/social step |
| `POST /turn-jobs/{job_id}/progress/claim` | Atomically claim one unsent progress event using a nonce |
| `POST /turn-jobs/{job_id}/progress/{progress_id}/ack` | Confirm the same claim after delivery |
| `GET /turn-jobs?connection_id=…&after_job_id=…&limit=…` | Message-job recovery page with `items` and `next_cursor` |
| `POST /turn-jobs/{job_id}/consume` | Claim the single terminal failure-notice attempt **before** sending |
| `POST /turn-jobs/cancel?connection_id=…` | Terminalize only one exact author/source/deployment/destination request; returns cancelled job IDs |

Mutation endpoints also require `connection_id` and existing Connector authentication.
Final successful responses reuse Runtime's existing delivery claim/acknowledgement protocol.
Unacknowledged progress claims and ambiguous final sends are not replayed. Failure-notice
consume returns 204 to one contender and 409 thereafter. A crash between claim and send can
lose a notice; it cannot safely be retried without transport reconciliation. Connector-only
poll expiry does not publish a false “generation failed” while the server job is still active.

Discord text controls are intentionally narrow until a Discord interaction command is installed:
the user must mention the Bot, reply to their own original human request, name exactly one
Character, and use the anchored form `Character cancel` or `Character replace: new request`.
The Connector forwards the original source message ID, author ID, deployment and exact Discord
destination; ordinary new messages and natural-language substrings do not cancel work. A cancelled
job is terminal and cannot store or deliver a late final reply. Cancellation cannot undo an
external effect that was already started; those outcomes stay uncertain and are never replayed.
It can also win the narrow interval after a final is generated but before Discord's durable
delivery claim: the server atomically makes that generated step non-deliverable. If the delivery
claim already won, cancellation reports no cancelled job because a Discord send may be in flight.
Explicit requests rejected by bounded Connector ingress receive a visible busy/expired reply;
Smart Participation collector work remains coalesced within its bounded burst window.

The Connector periodically scans bounded recovery pages, including pages whose records have
all lost authorization, and reattaches by job ID without calling generation again. Successful
jobs are selected only while their Runtime step remains generated and deliverable. Social turns
retain their existing durable social recovery. Source-message deletion or missing current
Discord access can still prevent recovery delivery.

On API shutdown, only that manager's owned work is stopped. A crash leaves no new worker
authorized to re-execute an uncertain operation; deadlines terminalize it. Startup/read checks
and a 60-second maintenance loop expire deadlines and retained records. Terminal jobs clear
their inbound request snapshot; retention/account deletion also remove progress. This is durable
status/result recovery, not transparent resumption of an interrupted provider call.

## Evidence and remaining validation

`test_mcp_gateway.py` exercises paginated catalogs, grants, schema changes, restricted validation,
unknown effects, inline images, and actual official-SDK transport with synthetic ASGI responses.
`test_mcp_conversation_integration.py` exercises model→discovery→invocation→final composition and
progress/idempotency. `test_slow_image_conversation.py` blocks a fake generator to prove progress
precedes completion and original-destination artifact delivery. `test_turn_jobs.py` covers API
scope, queue saturation, claims, shutdown, retention, and recovery past large/revoked histories.
Connector Vitest covers polling/progress/terminal claims and recovery pagination.

Independent source review found and drove fixes for admission, response bounds, delivery claims,
retention, and recovery starvation. These offline checks do not prove live provider compatibility,
natural dialogue quality, Discord delivery under real outages, PostgreSQL contention, or a full
adversarial Red Team exercise. Those remain explicit preview/release validation, not assumed passes.
