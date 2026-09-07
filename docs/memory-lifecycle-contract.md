# Memory lifecycle and owner-management contract

Status: implementation contract for the R12/R17 reliability follow-up. Source, persistence
schemas, and tests remain authoritative for exact behavior.

## Boundaries

`ThreadWorkingState` is transient scratch for one Conversation Thread. It can hold a current
object, unresolved questions, waiting state, active entities, and opaque media references. It is
not an Episode, Belief, or replacement for source evidence.

Episodes describe what happened and Beliefs describe what is currently believed. Both retain their
own provenance and revision history. Archiving scratch never deletes or rewrites either one.

## Retention matrix

| Record | Current lifecycle | Prompt/recall eligibility | Deployment deletion | Account deletion |
| --- | --- | --- | --- | --- |
| `ThreadWorkingState` | Active scratch expires after six hours; expiry or checkpoint archives it. Archived records remain derived lifecycle history. | Only active and unexpired state can enter `ContextResolverV3`. | Unchanged; deleting a deployment removes delivery configuration, not server/thread source state. | Deleted with the Intelligence v3 owner lifecycle. |
| `ConversationEpisode` | Active Episodes close on inactivity (30 minutes) or explicit/size checkpoints. Closed Episode provenance remains durable. | Episode retrieval remains separately scope and perception checked. | Unchanged; an Episode can record a server conversation independently of a deployment's current delivery target. | Deleted with the Intelligence v3 owner lifecycle. |
| `Belief` | Active/provisional/disputed claims are revisable. Superseded, rejected, and expired versions remain history. | Only current, valid claims are eligible; rejected/superseded/expired records do not become current facts. | Unchanged; a scoped Belief is not silently destroyed when a deployment is removed. | Deleted with the Intelligence v3 owner lifecycle. |
| Raw message/media evidence | Source provenance, outside derived scratch cleanup. | Recalled only through existing scoped/perception contracts. | Unchanged. | Governed by its owning source/account lifecycle, not this maintenance service. |

The stated deployment behavior is deliberately non-destructive. A future product decision to
purge a Character × server scope needs an explicit impact preview and a dedicated lifecycle path;
it must not be inferred from deployment removal.

## Maintenance

`ConversationRuntimeMaintenanceService` is a lifespan-supervised loop. Each pass first finds only
owners with active Episodes, calls their owner-scoped inactivity checkpoint, then archives expired
working state. A repeated pass has no additional lifecycle transition: closed Episodes are no
longer selected and archived scratch is no longer active.

The `ConversationRuntimeRepository.working_state` read boundary also checks `status` and expiry.
It archives an expired active record before returning `None`, so a delayed maintenance pass cannot
put stale scratch into a Character prompt.

## Owner management endpoints

Owner-facing deployment routes provide review, correction, rejection, and forgetting for a single
exact `owner_id + character_card_id + connection_id + guild_id` Belief:

- `GET /api/deployments/{deployment_id}/beliefs/{belief_id}` reviews the scoped record and its
  provenance references.
- `POST .../correct` runs the existing Belief authority/revision policy against only the selected
  scoped record. It records a revision event without manufacturing raw evidence.
- `POST .../reject` rejects a learned Belief; authored Beliefs retain their existing protection
  from automatic rejection.
- `POST .../forget` is an explicit owner action. It marks even an authored Belief rejected, so it
  leaves history and source evidence intact while excluding it from future current-fact recall.

Every route resolves the deployment under the authenticated owner and uses an exact scope match.
A valid identifier from another owner, Character, connection, or guild receives the same `404`
response and cannot be mutated by an administrator of a different account.
