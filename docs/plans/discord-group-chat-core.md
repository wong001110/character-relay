# Discord group-chat core simplification

Status: **ACCEPTED DESIGN / IMPLEMENTATION IN_PROGRESS — see PROJECT_STATE.md**.
Planning baseline: `3cd183d460812d16cfb0c6d8dbae305d8ef61363` (PR #205).
Accepted discussion consolidated on 2026-09-21. Progress belongs only in
[PROJECT_STATE.md](../../PROJECT_STATE.md); coding policy is [AGENTS.md](../../AGENTS.md).

The original PR #206 recorded requirements only. The user has now authorized execution on the
separate PR #207 branch; current evidence is in PROJECT_STATE.md. This plan supersedes older target designs for the
behaviors below. Existing safety, deployment and evaluation contracts remain unless explicitly
changed with equivalent or stronger verified protection.

## Product goal and exclusions

Build maintainable, affordable, distinct characters that participate appropriately in Discord
**guild group channels and native Threads**, not perfect human cognition. Multiple humans and
multiple roles share a room without becoming one user, one preference profile or one authority.
Occasional clarification and imperfect long-term recall are acceptable; wrong-person answers,
forced participation, private-data mixing and replayed external effects are not acceptable shortcuts.

Keep character authoring/versioning, Discord identities, bounded proactive participation, tools,
notes, practical observation and offline evaluation. Remove Roast-specific activities and
unnecessary mandatory pre-generation/background intelligence. Do not add group-DM/DM delivery,
voice/realtime streaming, local embodiment, a new multi-agent platform, a memory vendor, or a new
database/service topology in this initiative. Existing private data still requires isolation;
privacy examples are not authorization to add an unsupported connector.

## Accepted decisions

### D01 — Optional participation, not an obligation

- Zero bots joining is a valid successful outcome. Candidate nomination is not a command to speak.
- Prefer explicit mentions, Reply sources and message-selection actions. Natural unthreaded chat
  remains supported using a small recent room window; do not require people to use Reply every time.
- For ambient discussion, cheap eligibility/cooldown checks may propose one candidate. That role
  uses its normal generation to choose a contribution or `ignore`; no extra mandatory judge.
- If that candidate declines, end this ambient attempt. Do not cycle through all roles until
  somebody speaks, randomly fill an empty selection, or announce silence to the room.
- Direct requests should be answered or clarified within authority/budget limits; failure or
  overload must not masquerade as deliberate character silence or silently erase the request.
- Interests and relationships may contextualize expression, but do not create a duty to interrupt.

### D02 — Bounded multi-role interaction

Allow role-to-role invitations and A -> B -> A. Initial configurable validation values are
**3 distinct roles, 6 visible speaking turns, 2 speaking turns per role** within a bounded
interaction before human re-engagement. These are upper bounds, not quotas or measured optima.
A platform-split long message is still one speaking turn. Reactions/stickers also consume an
appropriate visible-action/rate budget and cannot bypass anti-spam limits.

Choose the next role against actual delivered messages; do not pre-generate an entire conversation.
Use a separate bounded generation-attempt/tool-loop budget, counting ignores, retries, repairs and
failed work. Add room-wide and requester-level rate/cost limits across interactions so new messages
cannot reset costs indefinitely. Explicit requests exceeding capacity need orderly bounded handling,
not an uncontrolled fan-out. Pending human requests take precedence over optional bot continuation.

### D03 — Group-chat provenance and fair attribution

Preserve stable human/role IDs, per-message Reply source, timestamps, edits/deletion status and
actual generated-response-to-source links. Display names are not identity. A webhook author is
resolved to the actual deployed role; another bot or a quoted message is not a human requester.

Keep trigger, selected response source, addressed participants, semantic subject and tool initiator
separate. Select relevant raw reply ancestors plus a bounded recent room window; missing/deleted or
inaccessible sources remain missing, not invented from a summary. Do not flatten simultaneous
conversations into a single user message or use the latest author as everybody's subject.

Prioritize actually involved people and roles in prompt aliases before unrelated deployed roles;
lists must not crowd out humans. Selection persistence/transfer must be reliable: failure cannot
silently change the response target or restore all unrelated recent messages. Legacy Topic authority
and a permanent semantic thread graph are not prerequisites for ordinary direct replies.

### D04 — Receive continuously; publish only fresh-enough drafts

1. Record the input snapshot/source revision used for generation; continue receiving/updating the
   room buffer while model work is queued or running.
2. Keep ordinary chat generation private as a draft. A draft is not delivered history, shared
   knowledge, social evidence or a reason to update relationships.
3. Immediately before delivery, inspect newly received relevant messages and source changes.
   A later source message cannot retroactively enter an already-running model request.
4. Clearly unrelated new discussion does not cancel the old request. Material clarification,
   correction or resolution may require an update or abandoning an optional contribution.
5. Coalesce relevant additions. At most **one contextual refresh** for an ambient attempt: the same
   role can directly revise the answer or ignore using the draft, source and new evidence. Do not
   run separate judge/writer/reviewer calls. No relevant change means no extra model call.
6. If an ambient draft becomes obsolete again, drop it and respect cooldown. A direct request stays
   tracked, with bounded retry/deadline and appropriate acknowledgement/failure handling; do not
   apply the ambient drop policy to silently lose a human request.
7. Stop/edit/cancel requires a matching source and authorized actor. Human priority pauses bot
   continuation; it does not give one member ownership of another member's task.
8. Never rerun completed or uncertain side effects to refresh wording. Preserve work/result IDs.
   Canceling generation, canceling a tool job and suppressing delivery are distinct transitions.

Typing indicators are optional hints, not content. V1 may ignore them. Any later courtesy wait is
bounded and must not permit starvation. Perfect ordering against a message arriving after the
final check is not promised; explicit source links and a later correction handle unavoidable races.

### D05 — Practical memory and bounded context

Ordinary context is the current role card, recent relevant raw messages, small explicit notes and
required runtime state. Rebuild/select it each turn rather than append every prior prompt/search
result forever. Cap and deduplicate retrieval results and tool loops; preserve valid tool-call/result
pairing and durable effect receipts when trimming context.

Stop automatic permanent self-fact extraction on every ordinary utterance. Support explicit
remember/correct/forget and operator editing with actor/scope checks. Preserve current corrections
without keeping the old always-on extraction pipeline under a new name. Third-party assertions
cannot overwrite somebody else's personal note; quotations and bot guesses are not self-reports.

Retain model-initiated memory/history/knowledge reads. History search must expose enough permitted
raw provenance to resolve Reply references, not pretend an Episode summary is a verbatim transcript.
Do not make a separate semantic judge, full entity graph or Knowledge Gap workflow mandatory.
A valid no-result is preferable to unrelated entities or recent memories as filler.

No periodic per-role summaries or global rolling "shared brain" in the initial implementation.
Add one small source-linked summary per equal-visibility room only if measured long-dialogue failures
justify it; size/interaction boundaries, not elapsed time alone, trigger it. Source evidence remains
rebuildable. Summaries cannot mix permissions, turn opinions into facts or recursively erase corrections.
This optional experiment is not a required prerequisite for P6.

### D06 — Keep relationships as short notes

Preserve authored relationships and small directional role -> person / role -> role notes, scoped
to their allowed room/context. No affinity/trust/comfort simulation, decay, permanent psychological
inference or closeness automatically derived from message counts. Do not generate an all-pairs matrix.
Only load notes relevant to the actually addressed participants, not every user or the last trigger.

Allow explicit preferences/corrections and an optional, low-frequency candidate update attached to
the normal role output. It is not a separate model call or background reflection service. Limit to
one update per relationship per interaction; validate visible source references, actor/target,
length and current record version. Invalid candidates are dropped without regenerating chat.

Auto-updates initially cover clear preferences and resolved interaction facts, not inferred dislike,
hostility or trust. Author-defined facts cannot be overwritten by ordinary chat. Bot repetition is
not independent evidence, and bot-only chatter must not upgrade closeness by volume. Keep simple
edit/clear/previous-version recovery. Relationship text influences expression, not admission,
authorization, data visibility or truth.

### D07 — Retire redundant ordinary-chat machinery

Remove automatic relation-score/event simulation writers, per-message memory extraction and
Entity -> Knowledge Gap -> Discovery dispatch from the ordinary chat path. Stop their scheduled or
background producers where no other explicitly supported use remains; hiding prompt output alone
is not retirement. Necessary current corrections, explicit notes and scoped recall must still work.

Make advanced Knowledge Fabric ingestion/sync, curiosity/discovery and research views optional,
not dependencies for a normal reply. Preserve useful existing knowledge tools, data lifecycle,
media handling, authoring and offline evaluation. No expansion of speculative cognitive modules.
Remove Roast creation UI, intensity settings, prompts, session APIs and dedicated scheduling after
safely ending existing sessions. Reuse general multi-role budgets, cancellation and delivery; do
not remove those with the activity. Historical records do not require destructive deletion.

### D08 — Discord transport and user operations

- Persist/fetch bounded Reply ancestors and actual response-source links, including webhook role
  output. Do not assume webhooks support native Reply just because bot messages do.
- Add a message-selection operation to ask a chosen role to answer, plus minimal pause/status/cancel
  affordances backed by existing APIs. Do not create a second command authorization engine.
- Distinguish definitely-unsent, partially-sent, delivered and uncertain outcomes. A webhook timeout
  or later-chunk failure cannot trigger a whole-message fallback that duplicates completed sends.
- Slow accepted tool work must not block ingress or the whole room queue. Keep generation/publication
  ordered where necessary and bounded; correlate asynchronous results to the original requester.
- Apply effective channel/private-Thread permissions to source fetching and output. Missing Message
  Content data is an operational condition, not a model comprehension failure; direct requests and
  ambient mode may require different fallback behavior.
- Update recent context on message edit/delete; rehydrate only bounded permitted history after restart.
- Apply explicit allowed-mention lists across bot, webhook, tool/progress and fallback output. No
  implicit everyone/role pings. Prefer brief contextual replies; do not spam progress updates.

### D09 — One interaction-level observation view

Reuse operation/turn/provider/job/delivery identifiers and existing trace stores. Show source/target,
input revision, involved roles, per-role outcome, retrieval source IDs, note changes, model attempts,
tool work, usage and delivered message IDs. No extra observer agent, mandatory trace SaaS or chain-of-
thought capture. Runtime reason codes are evidence; a model's optional reason is only self-report.

Distinguish no candidate, role ignore, capacity stop, stale draft, replacement, canceled request,
provider/tool failure and delivery uncertainty. Record keep/refresh/drop plus extra calls for D04.
Correlate parallel human requests rather than overwrite the room with the most recent one.
Count all attributable generation/repair/fallback/tool-follow-up work. Unknown usage is not zero;
provider usage and estimated monetary cost are separate. Show trace loss/incompleteness without
letting diagnostic failures alter authoritative job/delivery state.

Daily default is metadata-first, not truncated prose disguised as summary. Raw prompt/transcript,
arguments/results and error bodies require explicit bounded debug scope, expiry, permissions,
view/export audit and redaction. Treat captures as multiple people's data. Avoid capturing raw data
at all when unnecessary; retention and note-forgetting are distinct operations.

### D10 — Shared-room security, not human-cognition simulation

- Runtime enforces owner, connection, guild, channel/native Thread, role, requester and destination
  scope. Same-room shared history is allowed; shared preferences or shared authority are not assumed.
- Author-allowed global background must be explicit. Reject cross-room/private data before it enters
  prompts, not by asking the model to keep a secret it already received. Summaries/indexes inherit scope.
- Ordinary members can manage their own eligible notes/jobs; room configuration and others' work
  require the corresponding authority. A relationship or a claim of being admin grants nothing.
- Bot-to-bot invitations authorize discussion only. Tool grants and cost approvals bind to the real
  requester and operation; check current grants before effects and sensitive delivery.
- Preserve Vault/credential boundaries, deny-by-default MCP grants/schema checks, outbound URL/DNS
  protections, resource limits, idempotency and Public Demo read-only enforcement.
- Imported cards, memory notes, webpages, tool results and other bots' text are untrusted data. No
  prompt-only security, self-promoted authority or paid-tool escalation through another role.
- Do not replace missing perception/authority evidence with broad server matches or an any-source
  summary check. Validate the actual permitted evidence unit and disclosure destination.

### D11 — Maintenance and Portal simplification

Daily surfaces should focus on characters, deployments/room controls, explicit notes/relationships,
tools and understandable diagnostics. Keep advanced research/evaluation accessible without making
it setup overhead for basic chat. Retain existing UI/data/accessibility contracts and real values.

Use feature ownership in [architecture.md](../architecture.md), not duplicate V-next runtimes.
Remove old imports, composition wiring, writers, scheduled tasks, routes, flags, help text and tests
that only enforce intentionally retired behavior. Preserve negative security tests and add a
replacement acceptance test before retiring an old correctness contract. Finishing with two active
systems or hidden legacy defaults is not completion; historical data may remain inert with a policy.

## Integration dispositions (not dependencies installed by this PR)

These are accepted research directions from the discussion, not promises about current upstream
versions. Work must check pinned versions, compatibility, maintenance and licenses before copying
code or adding a dependency; justify new services or recurring cost separately.

| Candidate / primary reference | Disposition |
| --- | --- |
| [discord.js WebhookClient](https://discord.js.org/docs/packages/discord.js/main/WebhookClient:Class) | Prefer reuse of the existing SDK for standard transport; test retry/partial-send semantics, do not assume exactly-once delivery |
| [llmcord](https://github.com/jakobdylanc/llmcord) | Borrow bounded Reply-chain/context strategy; retain Character Relay identity, webhook source links and scope checks |
| [SillyTavern group chat](https://docs.sillytavern.app/usage/core-concepts/groupchats/) | Borrow shared history/current-speaker card and manual role controls; do not copy mandatory/random filler participation |
| [Kindroid customization](https://kindroid.ai/v2/docs/customizing-personality/) | Design reference for short relationship/background text, not a runtime/service integration |
| [AstrBot Favour Ultra](https://github.com/nuomicici/astrbot_plugin_Favour_Ultra) | Borrow only the optional update-in-normal-response idea; no numerical affection, punishment, exclusivity or separate plugin runtime |
| [Character Card V2](https://github.com/malfoyslastname/character-card-spec-v2) | Thin draft import/export adapter when justified; preserve unknown data safely and never import tool authority |
| [SearXNG API](https://docs.searxng.org/dev/search_api.html) | Optional controlled search provider adapter; public-instance JSON availability and hosting cost must be verified |
| [LiteLLM](https://docs.litellm.ai/) | SDK only if measured provider-adapter duplication warrants it; no automatic second proxy/auth/quota platform |
| [AstrBot](https://docs.astrbot.app/en/platform/discord.html) | Replacement research only, not layered into the current runtime |
| [OpenTelemetry GenAI](https://github.com/open-telemetry/semantic-conventions-genai) | Reuse useful metadata conventions; no mandatory collector/backend or raw content logging |
| [Discord messages](https://docs.discord.com/developers/resources/message), [Threads](https://docs.discord.com/developers/topics/threads), [commands](https://docs.discord.com/developers/interactions/application-commands) | Verify native capabilities/permissions against current official docs before implementation |

## Checkpoints and evidence gates

These are suggested coherent checkpoints, not fixed agent topology or a detailed function blueprint.
The main agent chooses how to execute, delegates selectively and revises boundaries with evidence.
Progress and branch-specific receipts are recorded only in PROJECT_STATE.md.

| Phase | Outcome / requirement coverage | Gate |
| --- | --- | --- |
| P1 | Baseline characterization, room/request provenance and threat boundaries (D03, D10); measured call/token baseline | Reproducible interleaved-human cases, scoped fixtures, unchanged/changed contract distinction; no invented baseline scores |
| P2 | Reply/source transport, event updates, restart and delivery/slow-work integrity (D03, D08, D10) | Connector + Python schema/route integration; duplicate/partial/uncertain send and isolation fault tests |
| P3 | Optional bounded multi-role flow and send-time draft checks (D01-D04) | Positive direct-response and negative ambient cases; A-B-A, concurrent additions, budget/fairness and no-effect-replay tests |
| P4 | Explicit memory, short relationship notes and actual retirement (D05-D07, D10-D11) | Actor/room note CRUD and candidate-update validation; no ordinary extraction/simulation/discovery calls; Roast entry points retired with history policy |
| P5 | Single observation view, practical Portal operations and justified reuse (D08-D11) | Correlated outcomes/cost, metadata default/raw debug auditing, real-data UI and affected browser journeys; record each adapter's adopt/defer rationale |
| P6 | Integration, physical ownership cleanup and retirement audit (all D01-D11) | Relevant full surface CI, targeted protected-logic mutation, same-model dialogue/cost comparison, failure/restart evidence, no obsolete active consumers |

Existing command reference: [developer guide](../developer/README.md),
[mutation testing](../mutation-testing.md), [manual/live validation](../manual-validation.md).
Use relevant tests and isolated environments; unavailable credentials, PostgreSQL, browser tools,
independent review or live permissions are recorded as unverified/blocked, never simulated passes.
Do not invent a numeric quality or savings target before measuring baseline. No production merge
or deployment is implied by this planning approval.

## Acceptance scenarios

Use synthetic fixtures with stable IDs, actual Reply links and multiple roles/humans. Add/locate the
proving tests during P1; these scenario IDs are requirements, not names of tests that already exist.

| ID | Scenario | Required observation |
| --- | --- | --- |
| A01 | Two humans discuss lunch; no bot is needed | Zero participation is valid; no round-robin attempts until someone talks |
| A02 | Explicitly ask Ann; unrelated Ning is present | Ann answers/clarifies, Ning need not speak; errors are not reported as chosen silence |
| A03 | Ann -> Ning -> Ann with useful new content | Re-entry works inside distinct-role, speaking-turn, attempt and room limits; may end early |
| A04 | Many deployed roles and two same-named humans | Real interlocutors retain aliases; stable identity and individual preferences do not merge |
| A05 | Interleaved game/lunch messages, with and without Reply | Correct source/recipient, bounded raw context, no last-trigger relationship substitution |
| A06 | Quoted "are you sure?", name-prefix collision, declarative "everyone" | No invented challenge or group invitation; direct requests still work |
| A07 | Selected-source persistence fails or required ancestor is inaccessible | No silent retargeting, no fallback to unrelated room content; explicit safe outcome |
| A08 | Related correction arrives during generation | Ingress updates immediately; original draft is not published unchanged; one ambient refresh maximum |
| A09 | Unrelated message/typing arrives during a direct task | No blind cancel/restart; typing has bounded/no effect; original requester/work preserved |
| A10 | Humans resolve the question before ambient send; revisions keep arriving | Optional draft can drop with a distinct reason and cooldown; direct request is not silently lost |
| A11 | Draft refresh follows a completed or uncertain paid tool | No duplicate tool side effect; draft text never becomes shared memory/evidence |
| A12 | Public room asks about private Thread/another owner's note | No unauthorized recall/disclosure; derived summaries and related artifacts obey the same boundary |
| A13 | One member reports another member's preferences or asks to cancel their job | No unauthorized overwrite/cancellation; attributed public discussion may still be read |
| A14 | Role asks another role to run paid tools / claims human approval | No authority laundering; current real requester grants and quotas apply |
| A15 | Legitimate relationship clarification, malformed candidate, bot-only repetition | Bounded source-linked update or safe rejection; no extra judge/retry and no volume-driven closeness |
| A16 | Multi-chunk webhook partially sends or times out after receipt | No whole-message resend on fallback; partial/uncertain state is explicit and recoverable |
| A17 | Restart, duplicate Gateway event, source edit/delete, permission revocation | Bounded permitted rehydration; deduplication and fresh source/grant checks; no duplicate publication |
| A18 | Missing Message Content data vs genuine irrelevant topic | Operational limitation distinguishable from semantic ignore |
| A19 | One visible answer required multiple calls and a format repair | All attributable attempts/usage counted; unknown is not zero; source-to-delivery correlation |
| A20 | Trace persistence failure and raw capture view/export | Diagnostic loss visible without corrupting job/delivery state; scope/expiry/audit enforced |
| A21 | Ordinary chat after retirement | No eager entity-gap/discovery, permanent self-extraction or social simulation; explicit note/recall still usable |
| A22 | Roast removed, ordinary multi-role chat retained | No active Roast UI/API/prompt/scheduler; general invitations, tools, cancellation and history still work |

## Done means one supported path, not renamed complexity

Map every decision and scenario to evidence or an explicit blocker. Remove old consumers and update
architecture.md to the actual moved source, not the proposed tree. Keep no second progress ledger,
mandatory wiki, fixed agent-role process or permanent legacy runtime fallback. Review changed API,
operator/UI docs and scheduled producers as well as prompt contents. Preserve evidence, backups and
safe lifecycle semantics; obtain explicit approval for any irreversible production purge.

The final report must separate code verification, deterministic replay, model/human quality evidence,
cost estimates and live deployment validation. Passing tests is not proof of perfect naturalness;
getting quieter is not proof of fewer wrong answers if direct human requests are being dropped.
