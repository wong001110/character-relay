# Discord group-chat core: lightweight Room Director refactor

Status: **ACCEPTED DIRECTION; EXECUTION AUTHORIZED 2026-09-30**.
Implementation baseline: `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (merged PR #207).
Progress and evidence belong only in [PROJECT_STATE.md](../../PROJECT_STATE.md).
Coding policy remains [AGENTS.md](../../AGENTS.md).

This revision supersedes the earlier implementation strategy, not its independent safety and
product acceptance requirements. The unpushed P3-P6 work described in old conversations is not
available source and is not counted as implemented. Do not finish that old architecture first.

## Authorization and product priorities

The user accepted the Reviewer recommendation, authorized documentation first followed by
phase-sized implementation, and requested Agent Continuity as an environment-side execution aid.
No merge, deployment, live database purge, new paid service or infrastructure expansion is
implicitly authorized. Railway may be inspected using the connected plugin without changing it.
Old conversation/derived data need not be migrated. Preserve authored character content when
practical through export/reimport, not a requirement to retain its old schema, IDs or runtime.
Do not silently discard cards because a legacy table is inconvenient. Record incompatible fields;
imported content cannot import credentials, grants or authority. Configuration/secrets are not
conversation data and are not casually deleted. Actual production reset is a separate cutover.

Priorities: correct participation, useful silence, correct target/topic, isolation, stable character
voice, useful on-demand recall, bounded cost/maintenance, and short bot-to-bot interaction. Complete
human cognition, continuous inner thoughts and numerical relationship simulation are not goals.

## Target responsibility chain

```text
Discord room events / bounded buffer
  -> runtime eligibility, permissions, budgets and explicit routing
     -> direct request: no Room Director call
     -> ambiguous batch: one bounded Room Director decision through the existing Free Token Pool
  -> runtime validates candidate, target, source revision and remaining authority
  -> focused context builder -> Character Agent
     -> optional memory.search / conversation.search / knowledge.search
     -> optional authorized tools / expression intent
  -> metadata/sparse expression resolver -> draft freshness -> safe Discord delivery
```

A decision is a proposal, not authorization. The Director has no tools, durable conversational
memory, private role notes, full private cards or progress/replanning ledger. Supply a bounded
room snapshot and public role descriptions; only the chosen Character receives its card and
scoped notes. Runtime owns access, effects, receipts and delivery. No second supervisor framework.

## Accepted decisions (D01-D11 retained as requirement identifiers)

### D01 — One participation authority with successful silence

Replace semantic participation and PlannerV3 scoring with explicit runtime rules and a lightweight
Room Director. Do not run embedding relevance before it or preserve the old planner as a permanent
fallback. Do not confuse the new Room Director with the existing post-admission Turn Director:
retire the latter's response/recall planning responsibility; the Character decides how to respond.

Model output is short JSON with exactly `speaker`, `target_message_id`, and `mode`:

```json
{"speaker": null, "target_message_id": null, "mode": "none"}
```

Speaking modes are `direct_answer`, `supplement`, `reaction`, `continuation`. A speaking decision
must contain an eligible deployment ID and a visible, targetable message ID. No explanation or
chain-of-thought is required. Unknown IDs, extra authority fields, malformed JSON, missing content,
provider failure and exhausted budget are operational outcomes, not successful NONE decisions.
The Character may still ignore; do not then try every other role until one speaks.

Explicit platform mentions, resolved Reply identity and role-selection actions bypass the model.
Display-name matches and quoted names are not reliable explicit-address authority. Handle multiple
explicit requests fairly and within capacity; do not silently discard all but one. Explicit mention
wins over a conflicting Reply recipient; preserve the reply as context, not as a second invented
request. An explicitly addressed unavailable role must not be replaced by an unrelated role.

Free Token Pool reuse is required; Jev is not. Use a qualified model set, strict validation, a total
deadline and bounded provider attempts. Log actual provider/model, attempts and unknown usage.
Do not silently fall back to paid credentials. Ambiguous provider failure fails closed; direct
requests remain tracked by their own route and failure/overload handling.

### D02 — Bounded multi-role interaction, not an autonomous society

Allow useful A -> B -> A against actual delivered messages. Initial validation ceilings remain
3 distinct roles, 6 visible speaking turns and 2 per role; these are configurable ceilings, not
quotas or measured optima. Also bound attempts, retries, repairs, tool loops and aggregate room /
requester cost. An ignore or failed call still consumes its appropriate attempt budget.
A split Discord message is one speaking turn; reactions/stickers consume visible-action limits.

Pending human requests take priority. A bot invitation creates no new human grant and cannot reset
budgets. Explicit valid invitations may route directly; ambiguous continuation uses the same Room
Director. Do not select based on unsent drafts, pre-generate a whole conversation, or regenerate a
completed/uncertain side effect to refresh wording.

### D03 — Source graph, not a mandatory semantic topic graph

Retain Discord native channel/Thread identity, stable authors/deployments, message IDs, Reply links,
edit/delete revisions, actual response-source links, requester and source evidence. Native private
Threads are access boundaries, not the old internally inferred ConversationThread.

Ordinary chat must not require permanent semantic Segment/Thread classification or embeddings.
Replace that dependency with a selected target plus bounded readable Reply ancestors and recent
messages. Multiple simultaneous topics need not be forced into a single permanent partition.
Consider bounded supporting message IDs only if replay demonstrates the three-field decision is
insufficient. No silent retargeting on persistence or permission failure.

Keep trigger, target, subject, addressed participants and tool initiator distinct. Resolve real
webhook role identity; same display names are not same people. Relevant humans must not disappear
behind a roster of unrelated roles. Missing/inaccessible sources remain missing, never reconstructed
as purported quotations from a summary.

### D04 — Continuous ingress, fresh drafts, no effect replay

Capture input revision; accept edits/deletions/new events while work runs. Drafts are private and
not delivered history, relationship evidence or memory. Recheck relevant source changes and grants
before sending. Unrelated messages do not cancel a direct request. Coalesce related corrections and
allow at most one ambient contextual refresh; a second obsolescence drops the ambient draft with a
reason/cooldown. Direct work stays tracked with bounded retries/deadline and failure handling.
Keep tool cancellation, generation cancellation and delivery suppression separate. Source-matched
stop/edit/cancel requires the authorized actor. Completed and uncertain effects retain receipts.
No separate judge/writer/reviewer chain for freshness; do not promise perfect race-free ordering.

### D05 — Small explicit notes and searchable history

Always-visible context contains the selected card, bounded current source context, relevant explicit
notes and required runtime state, not all recalled results forever. The Character chooses recall.
Retire ordinary automatic permanent extraction, the full Belief lifecycle as a chat prerequisite,
and per-character rolling summaries. Explicit remember/correct/forget and operator editing retain
actor, subject, role, visibility, source and version checks. One user's claim cannot rewrite another
user's preference. Generated repetition is not independent evidence.

Keep searchable source-linked history, but do not require the current Segment-driven Episode
projection. Bounded equal-visibility history chunks are sufficient initially; summaries are optional
retrieval optimizations, not mandatory per-message model work or verbatim evidence.

Embedding belongs in retrieval only. Raw recent messages are not embedded on every arrival. Build
note/history indexes in bounded batches; searches must not synchronously backfill every missing
candidate vector. Exact/sparse retrieval can work while an index is pending. Namespace by provider,
model, dimension and version; never mix spaces. Old vectors may be discarded. Prefer a configurable
remote embedding adapter after consumer isolation, without adding unapproved recurring cost.
Audit Tool Retrieval, RAG, expressions and media consumers before removing FastEmbed dependencies.
Knowledge Fabric advanced ingestion stays optional, not a prerequisite for ordinary replies.

### D06 — Short directional relationship notes

Replace familiarity/affinity/trust/comfort, baselines, deltas, decay, SocialEvent and Impression
simulation with short authored or explicit-source notes. No all-pairs matrix or bot-volume closeness.
Load only relevant permitted subjects; notes affect tone, never participation authority or grants.
Initial writes are explicit operations or operator edits. Optional bounded candidates attached to a
normal Character output may be considered later only with source/version/actor checks, no additional
judge call, and no overwrite of author-owned facts. Keep correction, clearing and previous-version
recovery; no requirement to convert historical scores.

### D07 — Retire machinery, resolve expressions after intent

Remove replaced imports, composition, writers, schedules, routes, flags, help text and tests that
only enforce retired semantics. Keep negative safety tests with replacement acceptance evidence.
Retire ordinary Entity -> Knowledge Gap -> Discovery dispatch and Roast-specific creation UI,
intensity, prompts, session APIs and scheduling. Preserve general jobs/invitations/delivery controls.

Character first decides whether to express; runtime resolves optional kind/action/intent/emotion
against catalog name/tags/semantic metadata/allowed actions and recent-use penalty. No mandatory
candidate catalog in every prompt, runtime expression embeddings or repeated vision. No match is a
valid omission. Optional vision runs once at ingestion when Discord metadata is insufficient; bound
resource use and validate catalog metadata as untrusted data.

### D08 — Discord transport and practical controls

Keep existing SDK and safe delivery foundation. Implement bounded permission-aware ancestor fetch,
response-source persistence and restart rehydration without replaying old requests. Webhook output
must have explicit source links; do not assume native Reply support. Message-selection ask-role and
minimal pause/status/cancel use existing authorization, not a second command engine.

Distinguish unsent, partial, delivered and uncertain; never whole-answer fallback after partial or
unknown sends. Slow accepted tools cannot block room ingress; correlate later results to the original
requester. Missing Message Content is operationally distinct from irrelevant content. Apply explicit
allowed mentions everywhere; no implicit everyone/role pings. This scope does not add DMs/group DMs,
voice, realtime streaming or embodiment.

### D09 — One observation path, real usage

Reuse operation/turn/provider/job/delivery IDs. Correlate source and revision, candidate and decision,
role outcome, recall IDs, note changes, model attempts, tool work, refresh/drop and receipts. No
observer agent or mandatory telemetry service. NONE, rule stop, model failure, role ignore, stale
draft, overload, cancellation and delivery uncertainty remain distinct. Unknown usage is not zero;
provider-reported usage, estimates, actual monetary spend and free-pool quota are separate.
Metadata is the default; no chain-of-thought collection. Raw captures need explicit scope, expiry,
permissions, redaction and view/export auditing. Diagnostic failure cannot mutate delivery truth.

### D10 — Runtime security and reset safety

Filter owner/connection/guild/channel/native Thread/role visibility before building any model input
or recall candidate list, then revalidate effects and sensitive delivery. Shared room history is not
shared preferences or authority. Preserve Vault, credential isolation, deny-by-default MCP grants,
URL/DNS protection, resource limits, idempotency and Public Demo server-side read-only behavior.
Cards/notes/webpages/tool results/bot claims are data, not elevated instructions. Media hints are not
proof the Character perceived content. No prompt-only privacy enforcement.

A future authorized reset stops old producers, drains or quarantines in-flight and uncertain work,
exports character content with a tested roundtrip, resets retired data, and establishes a new ingress
watermark. Do not rehydrate old triggers as new requests. New runtime still preserves new evidence.
No auto-purge on ordinary application startup or implicit database reset during this refactor.

### D11 — One supported path and maintainable daily UI

Keep the existing Python/Discord/Portal deployable surfaces and PostgreSQL topology. Do not add
AutoGen runtime, Supervisor package, Jev, a second orchestration platform, new cognition agents or
continuity infrastructure inside the repo. Reuse native/library patterns after checking licensing,
compatibility and the actual behavior; do not copy a framework's forced-speaker fallback.
Daily UI focuses on characters, deployments/room controls, explicit notes, tools and correlated
diagnostics. Advanced research/evaluation can remain optional. Remove obsolete configuration and UI
instead of merely hiding it. Retain real API data and existing accessibility contracts.

## Reuse decisions and primary references (checked 2026-09-30)

| Reference | Adopt / reject |
| --- | --- |
| [AutoGen SelectorGroupChat](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html) | Borrow public role descriptions, bounded shared evidence and candidate constraints. `selector_func` returning None delegates to its default selector; it is not our successful silence. No runtime dependency. |
| [llmcord](https://github.com/jakobdylanc/llmcord) | Borrow bounded Reply-chain strategy; preserve our owner scope, webhook provenance, jobs and grants. Pattern reference, not copied code. |
| [SillyTavern group chat](https://docs.sillytavern.app/usage/core-concepts/groupchats/) | Borrow shared history/current-speaker card; reject random filler when no character activates. |
| Existing discord.js, Pydantic, provider/Utility Gateway and LangGraph | Reuse existing implementation mechanisms. Do not introduce a new framework merely to select a speaker. |

Before copying code or adding dependencies, inspect upstream license, maintenance and pinned API.
Further external research informs implementation; it is not evidence that our quality gate passed.

## Revisable phases and gates

These are new refactor phases, not completion claims for the earlier P1-P6 work.

| Phase | Outcome | Required evidence |
| --- | --- | --- |
| P0 | Commit this accepted direction, replacement map and current baseline before source work | Documentation-only diff; current user authority and source baseline reconciled |
| P1 | Executable three-arm replay, strict decision/outcome contract, direct-route and scope fixtures | Current planner A vs rules-only B vs rules+Director C; no invented measurements; counterexamples and report integrity tests |
| P2 | Runtime source/provenance and direct routing; Room Director provider wiring | Scoped ingress -> admission -> source persistence tests; target validation and free-only bounded failure paths; no live ambient enable before quality gate |
| P3 | Character-owned decisions and focused context; retire semantic participation, old Turn Director and mandatory semantic thread machinery | Real entry/composition tests, no eager embeddings/extra planning, source and media boundaries preserved |
| P4 | Explicit notes/history, relationship replacement, retrieval indexing/namespace and sparse expressions | Scoped CRUD/search, long-history recall, corrections/revocation, no synchronous bulk embed, no runtime dense expressions |
| P5 | Bounded bot continuation, draft freshness, slow-job separation and daily observation/Portal | A-B-A, concurrency, permissions, uncertain effects, real-data UI and changed browser journeys |
| P6 | Reset/card roundtrip rehearsal, full retirement/dependency audit and integration closeout | Disposable DB tests; no replaced consumers/flags/routes; full applicable CI, protected-logic mutation, measured quality/cost and documented gaps |

Phase order may change for independent work, but do not silently omit requirements. P1 infrastructure
may be implemented while human-label and real-provider gates remain open. A failed/unavailable
Director quality gate does not require maintaining the old planner forever: a coherent future cutover
may run direct-only with ambient participation disabled and explicitly documented. No hidden fallback.
No phase implies merge, deployment or production reset authorization.

## Replay design and acceptance evidence

Target 200-500 distinct decision points (initial target 300), covering EN/CN, 2-3 simultaneous topics,
mentions/Reply conflicts, multiple explicit requests, legitimate NONE, direct responses, corrections,
bot continuation, unavailable content and permission boundaries. Synthetic seeds may test mechanics,
but are explicitly unreviewed until a human labels them. Templated variants are not independent
conversations. Split by conversation/family, never random individual turns; freeze heldout data and
record dataset/prompt/source/model identities. Allow multiple acceptable speaker-target pairs.

Compare A (current production planner path at a pinned commit), B (deterministic direct-only), and C
(the same deterministic routing plus Free Token Pool Director). A simplified/static adapter is not the
production baseline; stored predictions require source/run provenance. Missing arms remain missing.
Measure joint speaker+target accuracy, speaker accuracy, target accuracy on speaking cases, NONE
precision/recall, wrong-topic participation, missed/partial direct responses, errors/invalid outputs,
logical calls versus actual provider attempts, input/output usage, latency percentiles, cold/warm
index work and cost. Include errors and missing outcomes in coverage; never reward failure as NONE.
Unknown usage must propagate. Report model changes/fallbacks separately. Run some end-to-end turns:
correct selection alone does not prove correct character behavior or delivery.

Promotion requires recorded human-reviewed heldout labels, comparable real-model runs, no protected
boundary regressions and explicit review of quality/latency/cost tradeoffs against A and B. Freeze
numeric thresholds after measuring the baseline, before evaluating heldout candidates. Do not pick
thresholds after seeing candidate results or assert savings from synthetic/provider-stub tests.

## Preserved acceptance scenarios

| ID | Scenario and required observation |
| --- | --- |
| A01 | Humans discuss lunch: zero participation is valid; no retrying roles until one speaks. |
| A02 | Explicit Ann request: answer/clarify or tracked failure; unrelated Ning need not speak. |
| A03 | Ann -> Ning -> Ann: useful re-entry within distinct-role, speaking, attempt and room limits. |
| A04 | Same-name humans/many roles: stable identities, individual notes and relevant aliases survive. |
| A05 | Interleaved topics with/without Reply: correct source and recipient, no latest-trigger substitution. |
| A06 | Quoted challenge/name collision/declarative everyone: no invented direct address or invitation. |
| A07 | Source persistence/access fails: explicit safe outcome, no silent retarget or unrelated fallback. |
| A08 | Related correction during generation: ingress updates; one ambient refresh at most. |
| A09 | Unrelated message/typing during direct work: no blind cancellation or authority change. |
| A10 | Resolved/repeatedly obsolete ambient draft: drop distinctly; direct work not silently lost. |
| A11 | Refresh after completed/uncertain tool: preserve receipts, no effect replay or draft-as-memory. |
| A12 | Private Thread/other owner note requested publicly: no leak; derived artifacts obey scope. |
| A13 | Third-party note overwrite/job cancellation: reject unauthorized write/cancel, retain attribution. |
| A14 | Bot claims approval/invites paid tool: no authority laundering or quota reset. |
| A15 | Note correction/malformed candidate/bot repetition: explicit validated edit or safe rejection, no simulation. |
| A16 | Partial/timeout multi-chunk webhook: no whole-answer resend; uncertainty stays recoverable. |
| A17 | Restart/duplicates/edit/delete/revoked access: scoped bounded rehydration, no duplicate publication. |
| A18 | Missing Message Content vs irrelevant topic: distinguish operational inability from chosen silence. |
| A19 | Repairs/fallbacks before one answer: count all attempts, retain unknown usage and correlation. |
| A20 | Trace loss/raw capture: diagnostics cannot corrupt jobs; scope, expiry and view/export audit hold. |
| A21 | Ordinary chat after retirement: no eager extraction/social/discovery; explicit notes/recall work. |
| A22 | Roast removal: no dedicated UI/API/prompt/scheduler; general multi-role jobs/history still usable. |

Additional refactor checks: invalid/foreign/deleted Director target, unqualified/paid fallback,
free-pool exhaustion, direct-mention conflict, duplicated/stale replay records, missing measurements,
heldout contamination, card import authority stripping, embedding-space mismatch, and physical
retirement of all replaced consumers. Requirement-to-evidence status belongs in PROJECT_STATE.md.
