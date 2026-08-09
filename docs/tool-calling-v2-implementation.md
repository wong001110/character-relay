# Tool Calling V2 — Implementation Notes

Tool Calling V2 adds event-driven and social capabilities while preserving the existing rule that the LLM proposes and Runtime remains authority.

## Phase V2.1 — `watch.condition` ✅

A condition watch is a persisted, deployment-scoped future trigger. It is not an unbounded autonomous agent loop.

Implemented contract:

- created by an admitted Character Deployment through `watch.condition`
- requires an explicit human-initiated turn
- owned by the authenticated account and bound to the originating deployment
- stores the concrete originating Discord channel/thread, including server-wide Deployment cases
- stores a bounded condition description plus a bounded notification message
- Runtime evaluates only on a configured schedule, never continuously
- individual watches cannot check more frequently than every five minutes
- one evaluation attempt is one bounded model/tool turn
- watches have explicit states: `active`, `triggered`, `expired`, `cancelled`, `failed`
- each watch has `next_check_at`, `expires_at`, `attempt_count`, and `max_attempts`
- the background evaluator reuses the Character model/provider credential but can use only Deployment-assigned read-only Tools
- triggering queues a real persisted Scheduled Reminder through the existing delivery path
- a character may not claim the condition triggered before Runtime persisted that transition
- no automatic Tool Result → RAG/Memory persistence

Safety/authority:

- owner + deployment scoping is mandatory
- destination comes from Runtime context rather than model-provided guild/channel IDs
- checks are rate-limited and minimum cadence is enforced by Runtime
- external reads reuse existing approved Tool capabilities rather than exposing unrestricted browser control
- background evaluation cannot call side-effect Tools
- the only side effect after a positive evaluation is the final persisted notification

## Phase V2.2 — `character.invite`

`character.invite` is a social coordination proposal, not direct participant injection.

Implemented proposal path on the V2.2 branch:

1. Smart Output creates prompt-local participant aliases such as `p1` / `p2`.
2. A Character may call `character.invite` with one of those aliases on a human-initiated turn.
3. Tool Runtime validates that the alias resolves to another Character Deployment that is:
   - owned by the same account,
   - active in the same Discord destination scope,
   - not excluded by Server/Deployment channel-category scope,
   - configured for Smart Participation,
   - not the inviting Character itself.
4. A successful Tool call returns only `proposal_status=pending_runtime_validation`; model-visible Tool output does not contain the raw Deployment ID.
5. Runtime keeps one bounded prompt-local proposal for the turn.
6. During Smart Output validation, Runtime materializes the proposal as the same existing Character mention primitive used by Character Relay today.
7. If the model simultaneously tries to mention a different Character, Runtime does not auto-expand the invite proposal.
8. The Discord Connector remains final participation authority through the existing bounded bot-tag continuation path: active candidate resolution, participation mode, unique-turn protection, maximum depth, and response budget all still apply.
9. Bot-authored continuation turns cannot call `character.invite`, preventing recursive invite trees.

The invited Character still decides its own response according to its Character Card/persona. A successful invite Tool call does **not** guarantee that the invited Character will speak.

## Delivery order

1. `watch.condition` persistence + bounded evaluator/delivery lifecycle. ✅
2. `watch.condition` Tool Registry exposure, deployment assignment, Provider Trace visibility, and regression coverage. ✅
3. Prompt-local `character.invite` proposal/validation model. ✅
4. Smart Output materialization through the existing participant mention path. ✅
5. Full Python/Web/Connector/Docker regression + deployed smoke checks. ⏳
6. Mark Tool Calling V2 complete in the main roadmap after V2.2 merges. ⏳
