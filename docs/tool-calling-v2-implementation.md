# Tool Calling V2 — Implementation Notes

Tool Calling V2 adds event-driven and social capabilities while preserving the existing rule that the LLM proposes and Runtime remains authority.

## Phase V2.1 — `watch.condition`

A condition watch is a persisted, deployment-scoped future trigger. It is not an unbounded autonomous agent loop.

Initial contract:

- created by an admitted Character Deployment through `watch.condition`
- owned by the authenticated account and bound to the originating deployment
- stores a bounded condition description plus a bounded notification message
- Runtime evaluates only on a configured schedule, never continuously
- one evaluation attempt is one bounded model/tool turn
- watches have explicit states: `active`, `triggered`, `expired`, `cancelled`, `failed`
- each watch has `next_check_at`, `expires_at`, `attempt_count`, and `max_attempts`
- triggering creates a future Character event/delivery; a character may not claim the condition triggered before Runtime persisted that transition
- cancellation/listing are Runtime operations, not roleplay
- no automatic Tool Result → RAG/Memory persistence

Safety/authority:

- owner + deployment scoping is mandatory
- destination is inherited from Runtime context rather than model-provided guild/channel IDs
- checks are rate-limited and minimum cadence is enforced by Runtime
- external reads reuse existing approved Tool capabilities rather than exposing unrestricted browser control
- side effects remain bounded to the final notification/delivery

## Phase V2.2 — `character.invite`

`character.invite` is a social coordination proposal, not direct participant injection.

Runtime will validate:

- inviter is an admitted participant for the current turn
- candidate character belongs to the same owner and is deployable in the current server/workspace context
- participant limit has room
- candidate is not already participating
- relationship/capability rules allow the invite
- redundancy/relevance threshold is met
- only one accepted invite expansion is allowed per coordination round

The accepted invite becomes a Runtime participant event and then flows through Smart Participation. The invited character still decides what to say according to its own Character Card/persona.

## Delivery order

1. Persist watch schema + repository + tests.
2. Add watch Runtime service and bounded polling/evaluation lifecycle.
3. Expose `watch.condition`, watch list/cancel operations, Provider Trace metadata, and Portal observability.
4. Add the participant-invite proposal/validation model.
5. Expose `character.invite` and integrate it with Smart Participation V3 coordination.
6. Run regression + live smoke, then mark Tool Calling V2 complete in the roadmap.
