# LangGraph Phase 5 — Durable Runtime

Status: implementation complete / full repository validation pending

## Goal

Phase 5 makes the Phase 3 Character Turn and Phase 4 Social Turn rollout safe across HTTP retries,
process restarts, and Discord delivery boundaries without moving Character Relay authority into
LangGraph.

The core rule remains:

> LangGraph owns orchestration. Character Relay owns authority. Existing services own implementation.

Phase 5 does not add another rollout environment variable. The existing cumulative mode remains:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=social_turn
```

Once both Character Relay Core and the Discord Connector run the Phase 5 code, `social_turn`
automatically uses the durable protocol.

## Why a business checkpoint instead of only a LangGraph checkpointer

A LangGraph checkpoint can persist graph state, but the important Phase 5 crash windows cross
systems that are not graph state:

```text
LLM / Tool proposal
→ Character Relay ToolRuntime side effect
→ Core HTTP response
→ Discord Connector
→ Discord REST / Webhook side effect
→ Core acknowledgement
```

A graph checkpoint alone cannot prove whether a reminder was already persisted or whether a
Discord message was already sent when a process dies between two of those boundaries.

Phase 5 therefore uses a small Runtime-owned durability ledger around the delivery-delimited
Phase 4 graph. LangGraph continues to decide graph transitions; the repository remains business
truth for idempotency, delivery ownership, and recovery.

## Durable Social Turn operation

Every human Discord source event receives a deterministic `operation_id` derived from:

```text
connection_id
guild_id
channel_id
thread_id
source_message_id
```

Retries of the same Discord event therefore resolve to the same operation instead of creating a
new workflow.

The durable operation stores only coordination required to resume:

```text
operation_id
operation status
source Discord location / message id
initial eligible deployment refs
available deployment refs
Social Turn cursor
continuation budget / max depth
bounded delivered-Character source metadata while the operation is active
```

It does not store provider credentials, System Prompts, RAG excerpts, Tool arguments, Tool
results, or raw provider request/response payloads.

## Delivery-delimited checkpoint

The Phase 4 invariant is preserved:

```text
Character A generates
→ A is actually delivered to Discord
→ A is appended to the conversation context
→ checkpoint advances
→ Character B generates with A visible
```

The Core does not checkpoint past an external Discord side effect before that side effect has
been acknowledged.

Each Character step has a stable `step_id` derived from:

```text
operation_id
step_index
deployment_id
```

A repeated step request therefore returns the already-generated response instead of rerunning the
model and Tools.

Generated reply payload is retained only while waiting for delivery. After acknowledgement the
cached response and temporary visible text are scrubbed. Completed operation source text is also
scrubbed.

## Tool side-effect idempotency

Read-only Tools may be retried normally. Side-effect Tools use one persistent side-effect slot per
Character step.

```text
operation_id + step_id + deployment_id
→ claim side-effect slot
→ execute existing ToolRuntime
→ persist completed result
```

If the same step is replayed with the same Tool and arguments, Runtime returns the persisted Tool
result instead of executing again.

If a process dies after claiming the slot but before Runtime can prove completion, the slot becomes
`uncertain`. Runtime fails closed instead of executing the side effect again.

The slot is intentionally independent of Tool name and arguments. If a crash causes a regenerated
model turn to propose a different side-effect Tool or different arguments for the same Character
step, Runtime treats that as `uncertain` rather than allowing a second external mutation.

This preserves the existing Tool Calling V2 rule that at most one side-effect Tool may complete in
a Character turn while extending it across retries and restarts.

## Discord delivery claim / acknowledgement

A generated Character response that requires a Discord side effect uses:

```text
Core generated
→ Connector requests delivery claim with nonce
→ Core persists delivery_claimed
→ Connector sends to Discord
→ Connector acknowledges sent message ids / outcome
→ Core marks delivered and advances checkpoint
```

Repeated claim requests with the same nonce are safe. Repeated acknowledgement after Core already
committed delivery is also safe.

### Uncertain delivery window

There is no transactional boundary shared by SQLite and Discord. Therefore a process can die after
Discord accepted the message but before Core received acknowledgement.

Phase 5 chooses at-most-once safety:

```text
restart sees delivery_claimed
→ step = uncertain
→ operation = uncertain
→ do not blindly resend
```

This may require reconciliation for that rare run, but it avoids duplicate Character messages and
duplicate social side effects.

If an acknowledgement response itself is lost after Core already committed it, a later
`delivery/uncertain` report cannot downgrade the already-delivered step.

## Restart recovery

At startup the durable repository normalizes interrupted local states:

```text
generating
→ failed / safe to regenerate

delivery_claimed
→ uncertain / do not resend

side-effect claimed
→ uncertain / do not execute another side effect
```

After Discord Connector state synchronization it asks Core for resumable Social Turn operations.
For `active` / `awaiting_delivery` operations it fetches the original Discord source message and
re-enters the normal message pipeline with recovery mode enabled. The deterministic `operation_id`
loads the saved cursor rather than starting over.

For thread-originated events the Connector fetches the actual thread channel before retrieving the
source message.

## Runtime Trace Explorer

Phase 5 promotes the earlier privacy-safe Runtime Trace contract into durable persistence.

The neutral contract lives below both orchestration and persistence:

```text
echo_masque.runtime_trace
├─ RuntimeTraceEvent
├─ RuntimeTraceSink
├─ TraceNodeKind
└─ TraceEventStatus
```

`orchestration.trace` remains a compatibility re-export. Persistence no longer imports the
orchestration package, avoiding a persistence → orchestration → API cycle.

Persisted trace data is classification-level only:

```text
trace_id
graph_run_id
operation_id
graph_name
node_name / node_kind / status
owner / deployment / Character Card refs
changed state-key names
bounded metadata pairs
bounded error
```

Forbidden from Runtime Trace persistence:

```text
raw Discord message content
System / user prompts
RAG excerpts
credentials / authorization headers
provider request / response payloads
Tool arguments
Tool results
```

The Super Admin Toolbox now exposes **Runtime Trace Explorer** with graph/status/operation filters
and per-node detail. It is separate from Provider Trace because the two answer different questions:

- Provider Trace: what happened at the model-provider boundary?
- Runtime Trace: how did Character Relay orchestration move through Context, Model, Tool,
  Authority, and Social continuation nodes?

Early-silent Character Turns that terminate in `turn_resolve` are explicitly recorded as completed
runs rather than being left `running`.

## Retention and privacy

Durable Runtime records are pruned with a bounded retention window. Temporary generated response
payloads and delivered source text are scrubbed as soon as they are no longer needed for recovery.
Runtime Trace stores only the privacy-safe contract described above.

The durable operation ledger is not Character memory and is not exposed to the model.

## Compatibility and rollout

No new environment variable is required.

Earlier modes remain valid rollback/isolation points:

```text
off
condition_watch
character_turn
social_turn
```

The Social Turn step endpoint remains backward compatible when no `operation_id` is supplied, which
allows Core/Connector rolling deployment without immediately breaking an older Connector.

Current production verification after merge should keep:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=social_turn
```

and verify:

```text
normal multi-Character turn
character.invite continuation
read-only Tool call
side-effect Tool call
Connector/Core restart between Character steps
Runtime Trace Explorer correlation by operation_id
```

## Phase 5 exit gate

- stable Social Turn `operation_id` for the same Discord source event;
- stable per-Character `step_id` and generated-step replay;
- one durable side-effect slot per Character step;
- no duplicate side effect after changed regenerated Tool/arguments;
- delivery claim and idempotent acknowledgement;
- delivery-claim crash becomes `uncertain` rather than duplicate resend;
- startup resume of active Social Turn checkpoints;
- thread source-message recovery uses the thread channel;
- temporary cached reply/source payloads are scrubbed after completion;
- Runtime Trace is durable and privacy-safe;
- early-silent graph runs reach completed status;
- no new `CHARACTER_RELAY_*` variable;
- existing Smart Participation V3, ToolRuntime, repositories, and Discord transport remain authority;
- full Python 3.12/3.13, Web, Discord Connector, Docker, and Railway Smoke gates pass.
