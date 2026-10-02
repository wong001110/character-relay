# Discord group-chat core: lightweight Room Director refactor

Status: **ACCEPTED DIRECTION; EXECUTION AUTHORIZED; IMPLEMENTATION NOT YET COMPLETE**.
Source baseline: `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (merged PR #207).
Direction accepted and execution reconfirmed in the current user request, 2026-10-01.
Progress and handoff: [PROJECT_STATE.md](../../PROJECT_STATE.md). Policy: [AGENTS.md](../../AGENTS.md).

This revision replaces the old participation/semantic-thread design, not its safety requirements.
The lost, unpushed P3-P6 work is not implemented evidence. R0-R6 below identify this refactor,
not completion of the previous P0-P6. Keep one supported production path at completion.

## Goal, scope and authority

Prioritize correct participation, silence when appropriate, correct source/recipient, isolation,
stable personality, useful on-demand recall, bounded costs and brief bot-to-bot interaction.
Do not simulate complete human cognition. Support guild channels and native Discord Threads;
DM/group-DM delivery, voice, embodiment, a new orchestration platform and new service topology
are out of scope. Preserve the existing Python, Discord connector and Portal surfaces.

The user authorized writing this direction first, then phased implementation, tests, commits and
an implementation PR. Routine in-scope choices need no repeated confirmation. No merge or live
deployment is authorized by this instruction. Data compatibility is not a requirement: old
conversation, belief, relation, episode and vector data may be discarded at a controlled cutover.
Prefer preserving portable character-card content; do not retain old schemas/runtime to preserve
cards. Auth, credentials, billing and infrastructure configuration are not conversation data to
silently erase. Actual production reset belongs to the separately controlled release/cutover.

Use Agent Continuity v0.4.0 outside the checkout for this assignment's execution state and evidence.
Do not install a continuity runtime, database, manifest, CI job or bootstrap dependency in the repo.
PROJECT_STATE.md remains the only current project progress record. Commit coherent batches,
not each edit; preserve recoverable source before ending an execution session.

## Target responsibility split

```text
Discord events -> bounded room buffer + message versions/provenance
  -> runtime eligibility / permissions / capacity
  -> explicit mention, Reply or selected-context action: direct route
     otherwise: one bounded Room Director decision via existing Free Token Pool
  -> runtime validates NONE or (speaker, target_message_id, mode)
  -> focused source context + selected Character card + small relevant notes
  -> Character Agent (content, optional recall/tools/expression, or ignore)
  -> sparse expression resolution + draft freshness + current grants
  -> existing safe delivery / receipts
```

Director output is a proposal, never authorization. Director has no tools, private per-character
memory, persistent chat session or full private cards. Input is a bounded permission-filtered
room snapshot, eligible public role summaries and relevant delivered-interaction state. Runtime
builds eligibility before the request and revalidates the result and current grants afterward.

Planned wire decision (strict fields, no rationale or chain-of-thought):

```json
{"speaker":null,"target_message_id":null,"mode":"none"}
```

A speaking decision requires an eligible deployment ID, a visible supplied message ID and a mode
from `direct_answer`, `supplement`, `reaction`, `continuation`. Runtime metadata (snapshot revision,
provider/model/attempts/outcome) is separate from model output. Only add bounded supporting source
IDs if replay demonstrates that target plus Reply ancestors/recent context is insufficient.

## Accepted decisions

### D01 — One participation authority; optional silence

Hard rules route clear requests without a Director call. Multiple explicit targets form bounded,
tracked requests; conflicting target signals must not silently discard or arbitrarily retarget one.
Names in quotations, prefixes, untrusted card text and mentions alone do not confer authority.
Ambiguous room bursts, not every raw Gateway event, may use the Room Director. No embedding
relevance, semantic candidate ranking or old Planner precedes/follows it. NONE is a successful
semantic choice, not a provider error. Do not randomly fill silence or try each role until one speaks.
The selected Character may still ignore; end that optional attempt without selecting another role.
Direct requests need answer/clarification or explicit operational status, not silent disappearance.

### D02 — Bounded multi-role interaction

Support A -> B -> A based only on successfully delivered messages, not planned drafts. Initial
validation ceilings remain 3 distinct roles, 6 visible speaking turns, 2 per role, plus independent
attempt/tool-loop, room and requester budgets. These are proposed ceilings, not shipped settings
or measured optima. Reactions/stickers consume visible-action budgets; ignores, retries and failed
work consume attempt budgets. New room events cannot indefinitely reset cost limits. Human pending
requests take priority. A bot invitation grants discussion only, never new tools, spend or consent.

### D03 — Provenance, not mandatory permanent semantic topics

Keep stable owner/connection/guild/channel/native-Thread/message/human/deployment IDs, timestamps,
Reply edges, edit/delete revisions and actual delivered-response-to-source links. Keep trigger,
selected source, addressees, semantic subjects and tool requester distinct. Display names are not IDs.
Retire the permanent embedding-based Segment/ConversationThread graph as a prerequisite to turns.
Native Discord Threads and source visibility remain real boundaries. Build a bounded current-turn
focus from target, permitted raw Reply ancestors and relevant recent messages. Missing sources
stay missing; no silent fallback to unrelated room content or summary-invented ancestry. Alias
budgets must prioritize actually involved humans and roles rather than unrelated deployments.

### D04 — Fresh drafts without replaying effects

Keep ingress active during queued/running generation and slow tools. Bind drafts to input/source
revisions; drafts are not delivered dialogue, shared knowledge or relationship evidence. Check
freshness immediately before sending. Related corrections/resolution may refresh or drop an
ambient draft; unrelated messages must not cancel direct work. At most one ambient contextual
refresh by the same Character, with no separate judge. Further obsolescence drops that optional
attempt with reason/cooldown. Direct work retains requester, bounded deadline/retry and status.
Stop/edit/cancel needs matching actor/source authority. Never rerun completed or uncertain tool
work to refresh wording. Cancellation of generation, tool execution and publication are distinct.
Typing is optional and cannot starve requests; no promise of perfect ordering after the final check.

### D05 — Small explicit notes and on-demand recall

Rebuild each turn's context from the selected card, bounded raw context, relevant small notes and
necessary job/temporal state. No ever-growing prompt, automatic per-message permanent extraction,
per-role rolling summaries or shared global brain. Character decides whether to use memory.search,
conversation.search or knowledge.search. Results are scoped, capped, deduplicated, source-linked;
no unrelated filler on no-result. Preserve tool-call/result pairing and effect receipts when trimming.
Provide remember/correct/forget and operator editing with actor/subject/scope/version checks.
Third-party reports and bot guesses cannot overwrite another person's note. Authored facts cannot
be overwritten by ordinary chat. Searchable history can use bounded equal-visibility source chunks;
Episode-as-searchable-history survives as a capability, not a required old Segment-derived schema.
Optional source-linked summaries require measured need, not a timer or recursive summary pipeline.

### D06 — Relationship notes, not numeric psychology

Replace familiarity/affinity/trust/comfort, baselines, deltas, decay and event simulations with short
directional notes. Load only relationships relevant to addressed participants. Preserve scope,
source, edit/clear and version checks; notes never affect permissions or participation authority.
Initial updates are explicit user/operator corrections, not an all-pairs writer. Any later ordinary-
output update must be bounded, source-backed and validated without another model call; bot-only
repetition is not independent evidence or a reason to upgrade closeness.

### D07 — Remove duplicated ordinary-chat intelligence

Retire per-message permanent extraction, social simulation/event producers and mandatory
Entity -> Knowledge Gap -> Discovery dispatch from ordinary chat. Keep supported knowledge
retrieval/ingestion optional. Remove Roast UI/API/settings/prompts/scheduler, not just visibility.
Remove the old character-internal Turn Director's reply/recall planning role: Character owns those
choices. Reuse Utility Gateway transport/quota/provider capabilities for the Room Director, not
its old TurnDirectorProposal behavior. No second supervisor framework or continuous inner thoughts.

### D08 — Transport, jobs and user controls

Keep permission-aware bounded source fetching/rehydration, edit/delete invalidation and duplicate-
event protection. Webhooks need actual response-source mapping; do not assume native Reply support.
Retain definitely-unsent/partial/delivered/uncertain distinctions. A later-chunk error or timeout
cannot resend a whole answer. Slow accepted tools cannot block room ingress; original requester,
job/result IDs and grants survive resumption. Reuse existing command auth for chosen-message/role,
pause/status/cancel operations. Apply explicit allowed-mention lists to all output paths, including
progress/fallback; no implicit everyone/role pings. Missing Message Content is an operational state.

### D09 — Observable outcomes and bounded provider routing

Reuse turn/operation/job/provider/delivery IDs. Distinguish semantic NONE, rules silence, Character
ignore, unavailable/timeout/malformed/invalid decisions, stale drafts, cancellation, capacity and
uncertain delivery. A failure is not a semantic abstention. Log model identity, prompt revision,
provider attempts, usage, latency, snapshot/target IDs and costs; unknown usage/cost is not zero.
One logical Director call may have multiple transport attempts; bound aggregate deadline/attempts
and count them all. Use only an evaluated Free Token Pool candidate set. No silent paid fallback.
Director failure ends optional ambient participation; it never revives the old Planner. Clear
requests remain on the direct path. Diagnostic failure must not corrupt authoritative execution.
Metadata is default. Raw captures require explicit scope/expiry/access/redaction/audit; no CoT.

### D10 — Runtime-enforced isolation and safety

Enforce owner, connection, room/native-Thread, character, requester and destination scope before
prompt construction and again at effects/delivery. Equal-room history is not shared preferences
or shared authority. Notes/summaries/indexes inherit visibility; explicit allowed global background
is distinct. Imported cards, recalled text, webpages and other bots are untrusted data. Preserve
credential isolation, MCP grants/schema validation, outbound URL/DNS protections, idempotency,
resource limits and Public Demo server-side read-only enforcement. Never rely on prompt secrecy.

### D11 — One supported runtime and practical Portal

Keep daily authoring/deployments/room controls/notes/tools/diagnostics understandable. Preserve
real-data APIs and UI/accessibility contracts. Remove retired imports/composition, routes, scheduled
producers, settings/env flags, help/docs and tests of intentionally removed behavior; retain negative
security tests and replace correctness tests before removing old ones. No indefinite dual-engine
mode or forwarding modules. R1-only benchmark adapters are evaluation code, never production fallback.

### D12 — Embeddings only behind retrieval

Remove semantic participation, conversation-structure and expression embedding from ordinary turns.
Do not merely replace FastEmbed with a remote client: existing query-time candidate cache misses
can create many passage embeddings. Raw message ingress stores text without per-message embedding.
Explicit note/history chunk ingestion may batch index. Retrieval filters scope first, uses exact/FTS/
sparse paths, and dense retrieval when appropriate; no-result is valid. Cold/incomplete indexes may
return sparse results and visible indexing status, not synchronously bulk-embed a history backlog.
Provider/model/dimension/version namespaces must not mix. Old vectors can be discarded; re-index into
new namespaces. Audit Tool Retrieval, RAG, Media Recall and other shared encoder consumers before
removing production FastEmbed dependencies. No unapproved provider subscription or hosting topology.

### D13 — Expression intent before catalog selection

Character first chooses no expression or a kind/intent/emotion/action. Runtime selects an allowed,
room-available emoji/sticker using names, aliases, intent/emotion, tags, semantic metadata and
recent-use penalty. No preloaded candidate catalog in every prompt, dense embedding or per-use
vision call. No good match means omit expression. Optional one-time cheap vision ingestion fills
missing catalog metadata; metadata/character output never creates permission to use an asset.

### D14 — Clean data reset and portable cards

Do not implement conversions for old relation scores, Belief state machines, semantic Thread IDs,
Episodes or vectors just for compatibility. Prefer a small card-content export/import boundary,
using existing format/spec support where suitable. Preserve authored content, not runtime authority,
secrets or incompatible schemas. If a field is unmappable, report it rather than retain old machinery.
Before any separately released reset: stop all old ingress/producers, settle or quarantine pending/
uncertain effects, identify exact stores and reset boundary, verify card export, then start only the
new supported path. Old messages must not replay as new tasks on restart. New source evidence and
new delivery receipts remain required even when historical data is discarded. No live purge in R0/R1.

## Reuse / reference decisions

Checked against primary references on 2026-10-01; patterns are not copied code or new dependencies.

| Reference | Adopt / reject |
| --- | --- |
| [AutoGen SelectorGroupChat](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html) | Adopt bounded shared-view selection and public candidate descriptions. Do not adopt runtime; selector_func None invokes model selection, not our NONE contract. |
| [SillyTavern group chats](https://docs.sillytavern.app/usage/core-concepts/groupchats/) | Adopt selected-speaker card/shared history. Reject random last-resort speaker and forced participation. |
| [llmcord](https://github.com/jakobdylanc/llmcord) | Reference Reply-chain context; keep our webhook identity, grants and visibility. Does not solve all unthreaded ambiguity. |
| [LangGraph Supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) | Borrow responsibility split only; keep existing LangGraph runtime, no supervisor package. |
| [Character Card V2](https://github.com/malfoyslastname/character-card-spec-v2) | Evaluate thin portable authored-content adapter; never import tool grants/credentials. |
| Existing discord.js, pytest, Utility Gateway, jobs/outbox and PostgreSQL | Reuse SDKs, tests and owned safety code before adding services or frameworks. |

Before adding any dependency or copying upstream code, inspect actual pinned version, license,
maintenance and compatibility. A reference does not warrant replacing our safety boundary.

## Refactor phases and gates

The main agent may split/reorder coherent slices with evidence, preserving all acceptance below.
No phase labels constitute permission to deploy, spend new money or silently lose source changes.

| Phase | Outcome | Exit evidence |
| --- | --- | --- |
| R0 | Direction, replacement map, baseline, data/card policy and source/evidence boundaries committed before implementation | Docs link/coverage review; no source/dependency/runtime change in this commit |
| R1 | Offline replay harness, strict decision/rules/validation spike, baseline adapters and 200-500 decision points | Rules/Planner/Director distinguished; synthetic vs human-reviewed labels distinguished; negative tests and metrics tested; real provider quality gate remains explicit |
| R2 | Source-focused context and direct routing, continuous ingress, permitted ancestry/restart and safe slow-job handling | Source/actor/destination isolation, conflicts, interleaved humans, edit/delete/restart, no duplicate/uncertain effects; direct route has zero Director calls |
| R3 | Replace selection with evaluated Room Director; retire old Planner/semantic participation/inner Turn Director; bounded bot continuation/freshness | Real pool model replay gate before ambient activation; A-B-A, attempts/cooldowns, target validation, one refresh and direct-request fairness; no old fallback |
| R4 | Explicit notes/history, note relationships, retrieval-only encoder boundary and sparse expressions | Scoped CRUD/recall/indexing tests; no eager extraction/social/discovery/embed on normal chat; cold-index and namespace tests; no extra expression calls |
| R5 | Portal/observation simplification and complete runtime/config/UI retirement | Real APIs/affected browser journeys; failure-vs-NONE/usage diagnostics; Roast and dead settings removed |
| R6 | Integration, deletion audit, card export/reset dry run and release preparation | Python/Connector/Portal/PostgreSQL and applicable mutation/fault checks; one runtime; clean start and card import on isolated store; no live release inferred |

An unqualified Director does not block independent safety/source work, but blocks ambient activation.
If quality is insufficient, use explicit routing/ambient disabled, not a permanent old Planner fallback.

## Replay design and promotion criteria

Compare (A) pinned current Planner, (B) deterministic direct routing only, (C) the same rules plus
Room Director. A deterministic fake encoder is not the production FastEmbed baseline; report it as
such. Fixtures include explicit/multiple/conflicting targets, NONE, interleaved topics, same names,
quotes, private scopes, missing content, bot-only loops, corrections, errors and capacity. Split by
whole conversation, never by near-duplicate message slices. Allow multiple valid (speaker,target)
pairs. Label provenance and review status must be recorded; generated labels are not human labels.

Measure speaker/target/joint accuracy, NONE precision/recall with explicit denominators, wrong-topic
participation, missed direct response, error rate, logical calls/message and per decision, physical
attempts, input/output tokens, p50/p95 including queue/retry, monetary cost with unknowns, cold/warm
retrieval separately and per-model drift. Report uncertainty and scenario groups, not just a mean.
Never exclude failures to inflate silence precision. Strict fixtures require zero cross-scope
admission, zero valid-direct-request loss, and zero uncontrolled retries/paid fallback. Compare model
quality on a held-out, human-reviewed set before claiming superiority; model suitability needs an
explicit report of tradeoffs and actual latency/budget, not a universal guessed threshold.

## Acceptance scenarios (carried forward; extended)

| ID | Scenario | Required observation |
| --- | --- | --- |
| A01 | Human lunch chat | NONE valid; no forced role or iterate-until-speaks |
| A02 | Explicit Ann, unrelated Ning | Ann response/clarification or tracked error; zero Director calls |
| A03 | Ann -> Ning -> Ann | Delivered evidence only; bounded roles/turns/attempts/room costs |
| A04 | Many roles, same-named humans | Stable identity and involved-human aliases; no preference merging |
| A05 | Interleaved topics with/without Reply | Correct speaker/target/focus; no permanent semantic-thread prerequisite |
| A06 | Quoted name/challenge, prefix collision, declarative everyone | No invented direct request, challenge or group invitation |
| A07 | Source persistence failure/inaccessible ancestor | Distinct safe failure; no silent retarget/context widening |
| A08 | Related correction during generation | Ingress active; stale draft not sent unchanged; one ambient refresh |
| A09 | Unrelated arrival/typing during direct task | No blind restart/cancel; original requester and work survive |
| A10 | Human resolution/repeated revision | Ambient drop has reason/cooldown; direct request remains tracked |
| A11 | Refresh after completed/uncertain tool | No duplicate effects; draft is not shared evidence |
| A12 | Private Thread/other owner note | Scope applied before prompts, summaries and retrieval results |
| A13 | Third-party preference/cancel claim | No unauthorized overwrite/cancel; public attributed text remains data |
| A14 | Bot claims consent or asks paid tool | No authority laundering or new grants |
| A15 | Relationship edit/malformed update/bot repetition | Validated short note or rejection; no numeric or repetition-driven inference |
| A16 | Partial webhook/timeout after receipt | No whole-answer resend; confirmed receipts and uncertainty survive |
| A17 | Restart/duplicate/edit/delete/revocation | Bounded permitted rehydration, source/grant recheck, no replay |
| A18 | Missing Message Content | Operational failure distinct from irrelevant-topic silence |
| A19 | Multiple attempts/repair for one reply | All attempts counted; unknown usage/cost not zero |
| A20 | Diagnostic write failure/raw capture | Job truth unaffected; scoped/expiring/audited access |
| A21 | Ordinary chat after retirement | No eager entity-gap/discovery/self-fact/social/semantic embed calls |
| A22 | Roast removal | No UI/API/prompt/scheduler entry; general role interaction survives |
| A23 | Invalid/timeout/empty/unavailable Director | Not semantic NONE; bounded attempts/deadline; no Planner/paid fallback |
| A24 | Multi-target/conflicting direct request | Deterministic documented handling; no lost target or arbitrary fan-out |
| A25 | Cold retrieval index/model switch | No query-time bulk backfill; sparse/no-result valid; spaces not mixed |
| A26 | Expression unused/no match/forbidden asset | Zero catalog work when absent; sparse choice only; invalid/no match omitted |
| A27 | Card export + clean isolated reset | Authored content portable, no grants/secrets imported; no schema lock-in |
| A28 | Pool model changes/failover | Actual model/attempts logged; only evaluated candidates; drift visible |
| A29 | Replay labels/splits/missing predictions | No test leakage, no fake human review, omissions/failures not scored as NONE |

## Completion

Production wiring, regression/fault/mutation evidence, removed consumers/config/docs and updated
architecture are required. Isolated classes/mocks/green synthetic tests alone are not completion.
Report actual source commit, local/CI/live checks, self vs independent review, limitations and
release state separately. All current progress belongs in PROJECT_STATE.md, not a second roadmap.

## Authorized extension (2026-10-02)

[Web Room Participant](web-room-participant.md) is accepted alongside this work. The user
authorized combined squash merge to main after implementation and verification. Live tests
remain user-owned; no failed code/integration gate is waived by that deferral.
