# Runtime replay validation

This validation deliberately uses synthetic Discord payloads and fake providers only. It records
deterministic Runtime and delivery outcomes; it does not assign a dialogue-quality score.

## Executed local evidence

| Journey | Formal boundary | Evidence | Observed assertion |
| --- | --- | --- | --- |
| Controlled MCP discovery, invocation, progress, unknown side effect | `PromptModelTarget` -> `ToolRegistry` -> bound turn progress | `tests/test_mcp_conversation_integration.py` | Progress is visible before blocked work, MCP visibility changes after discovery, an unassigned tool cannot run, and an unknown write is not retried. |
| Durable normal/social replay and delivery | Runtime operation/step repository | `tests/test_runtime_durability.py` | Stable operation identities replay generated output; claimed/uncertain delivery is not blindly re-executed. |
| Normal message API through Runtime and delivery | Connector message API -> Runtime -> delivery claim/ack -> repeated ingress | `tests/test_runtime_journey_replay.py` | Actual API reply carries durable operation/step IDs; delivery is acknowledged and replay returns delivered state; an unassigned channel receives no active deployment. |
| Actual connector ingress and graph dispatch | Discord connector API routes | `tests/test_character_turn_graph_wiring.py`, `tests/test_social_turn_graph_wiring.py` | The request reaches the configured graph runner with Runtime-owned IDs. |
| Async connector job lifecycle | job API -> worker -> existing Runtime route | `tests/test_turn_jobs.py` | Scoped polling, early model-authored progress, queue bounds, shutdown/timeout uncertainty, replay retention, and recovery delivery state are durable. |
| Fabric supervised failure/restart | scheduler and invalidation worker loops | `tests/test_runtime_reliability_review.py` | Bounded retries surface failure to the supervisor; a controlled restart starts a fresh loop. |

The original local environment had no Docker or PostgreSQL endpoint. Subsequent GitHub CI run
`34134120102` at `9ccc773` passed all six selected PostgreSQL foundation tests, including
quota contention and owner-admission locking. That is CI evidence, not a local PostgreSQL pass
or proof of real Discord outage/cross-process delivery. The production-image Portal journey
uses synthetic API fixtures and does not establish live end-to-end backend behavior. Current
correction and browser-gate evidence are in `docs/reliability-gap-closeout.md` and PR #204.

## Required replay manifest fields

For a future isolated preview replay, retain only synthetic or approved redacted values for:

- ingress connection/guild/channel/thread/deployment IDs;
- admitted tool IDs and tool results, excluding credentials;
- memory/correction evidence references and their scope;
- durable operation/step IDs, delivery claim outcome, and elapsed timing;
- progress claim/ack outcome and final reply/artifact outcome.

Run ordinary and Social Turn paths separately. Include a scoped correction, a missing MCP grant,
an intentionally delayed tool, a failed tool, and an uncertain external-write simulation. Record
the observed outcome and timing; assess conversational naturalness separately through calibrated
human review.
