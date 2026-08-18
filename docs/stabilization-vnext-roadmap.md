# Character Relay — Stabilization vNext Repair Roadmap

Status: **IN PROGRESS — OWNER ACCEPTANCE REQUIRED BEFORE MERGE**

Branch: `agent/stabilization-vnext`
Base: `main` at `dc2f4e65055f7b94d27bb7c774315adb1be8baf0`

This roadmap records the accepted repair direction after reviewing the current Conversation Intelligence, Discovery, Relationship/Social Intelligence, Media Understanding, and Utility Free Pool behavior.

The goal is not to add another independent brain. The goal is to make the existing runtime observable, socially meaningful, provider-safe, and suitable for fast interleaved Discord group chat.

## Working rules

- Keep Runtime authority deterministic for permissions, credentials, side effects, budgets, cooldowns, Deployment scope, and platform routing.
- Character roleplay providers remain responsible for in-character wording, not system classification.
- Utility LLMs are allowed to interpret ambiguous system-level structure but never receive Tool/credential/side-effect authority.
- Prefer evidence reuse across downstream consumers instead of repeated LLM interpretation of the same Burst.
- Do not merge this branch automatically. Owner acceptance is required after implementation and validation.
- Changes are implemented and validated in meaningful phase batches; do not create a commit/test cycle for every small edit.

---

# Phase 0 — Baseline reconciliation and acceptance contracts

## Goals

1. Reconcile repository documentation with actual merged behavior.
2. Record the new Definition of Done: a runtime feature is not product-complete until required Portal observability/control surfaces exist.
3. Add regression fixtures for the failures observed during owner review.

## Acceptance

- [ ] Current merged Discovery runtime is documented as runtime-complete but Portal-incomplete until Phase 2 lands.
- [ ] Utility/Media provider errors are separated by failure class rather than collapsed into generic protocol failures.
- [ ] Topic regression fixtures include rapid topic changes and interleaved group-chat discussion.
- [ ] Existing raw Discord/source evidence remains authoritative and is not deleted by migration work.

---

# Phase 1 — Provider Capability & Structured Output Hardening

This phase fixes repeated Media Understanding structured-output failures and Free Pool routing to models that do not actually support the required modality/output/tool capability.

## 1.1 Model capability registry

Separate Character Relay consumer capabilities from provider/model capabilities.

Consumer examples:

- `semantic_judge`
- `topic_intelligence`
- `memory_intelligence`
- `participation_tiebreak`
- `tool_continuation`
- `media_understanding`
- `structured_summary`

Model capabilities must describe actual transport/protocol support, including at least:

- text input
- image input
- multi-image input
- native video / video URL input
- data URI image input
- JSON object mode
- JSON schema mode
- native tool calling

Capability evidence should distinguish:

- declared/configured capability
- probe result
- runtime-observed result

A capability failure must not make an otherwise healthy text model globally unavailable.

## 1.2 Provider failure normalization

Quota exhaustion must not be inferred from HTTP 429 alone.

Normalize provider responses using:

- HTTP status
- rate-limit/quota headers
- JSON error envelope
- provider error code/type/message
- provider-specific rules where required

Normalized failures must distinguish at least:

- `rate_limited`
- `quota_exhausted`
- `free_tier_exhausted`
- `billing_required`
- `insufficient_balance`
- `authentication_invalid`
- `model_unavailable`
- `model_not_found`
- `capability_unsupported`
- `temporary_unavailable`
- `protocol_error`

`200 OK` responses containing an error envelope must be classified before chat-completion parsing.

For FREE ONLY members:

- billing/payment-required responses must never silently become paid use;
- a resettable free quota may re-enter routing after `reset_at`;
- billing-required/non-resettable access remains blocked until configuration/probe state changes.

## 1.3 Capability-scoped routing and health

Free Pool routing must consider:

`Access State + Capability State + Health + Quota`

Examples:

- vision unsupported -> skip only for media requests;
- JSON mode unsupported -> use a compatible structured-output strategy;
- native tools unsupported -> do not route native Tool calls there;
- text Judge may remain healthy even if the same model cannot process images.

## 1.4 Media structured-output runtime

Media Understanding should use the strongest output contract supported by the selected model:

1. JSON Schema derived from `MediaAnalysis.model_json_schema()` where supported;
2. JSON Object mode where supported;
3. strict prompt-only compatibility mode otherwise.

Prompt-only mode must specify exact field types, no prose/markdown, arrays of strings, required `summary`, and stable snake_case keys.

Parsing should distinguish:

- perception/provider failure;
- valid perception with malformed serialization;
- schema validation failure;
- capability mismatch;
- quota/access failure.

Add bounded repair before abandoning a useful vision result:

- fenced/leading prose JSON extraction;
- deterministic safe normalization where no facts are invented;
- optional cheap text-only schema repair that cannot add new media facts;
- only then try the next provider.

## 1.5 Media/Utility integration

Media Free Pool calls must report capability/access/health outcomes back into shared Utility routing state rather than bypassing failure learning.

## Acceptance

- [ ] A model that supports text but not image input remains eligible for text Utility work.
- [ ] `billing_required` is not retried as a transient protocol error.
- [ ] resettable quota exhaustion is retried only after the recorded reset/cooldown.
- [ ] `200 + error JSON` is classified correctly.
- [ ] Media analysis can recover safe malformed JSON without a second vision call where possible.
- [ ] Media output uses schema/object/prompt-only fallback according to model capability.
- [ ] Unsupported JSON mode does not poison unrelated model capabilities.

---

# Phase 2 — Discovery Product Surface

The current Discovery runtime already provides Deployment-scoped profiles, sources, browsing sessions, exposures, decisions, and share records. The product surface must expose and control that behavior.

## 2.1 Deployment Discovery controls

Discovery belongs to the Deployment lived runtime, not the reusable Character Card.

New Deployments must remain:

- Discovery OFF
- YouTube disabled
- Bilibili disabled

Deployment Editor must expose:

- Discovery enabled/disabled
- allowed sources per Deployment
- sharing behavior: Shadow / Review / Auto
- daily share budget / cooldown where applicable

UI semantics must separate:

- `Discovery enabled` = whether this Deployment may browse external content;
- `Allowed Sources` = where this Deployment may browse;
- Character interests = what it prefers once browsing is allowed.

Do not automatically enable a platform from Character interests.

Bilibili remains Experimental and additionally requires the global experimental gate.

Turning Discovery OFF should stop runtime activity without deleting the saved per-source choices; a newly created Deployment still starts with all sources false.

## 2.2 Discovery Observatory

Add a Discovery page to the Deployment Workspace / Server Notebook.

The observatory should support Deployment filtering and expose:

- current Discovery mode/state
- source availability
- recent browsing sessions
- candidate / notice / open / watch / engage funnel
- selected content and subjective exposure reason
- decisions / motivation / confidence
- Topic/Episode/person association evidence
- Shadow WOULD_SHARE evidence
- pending Review shares with approve/reject
- Auto delivery history
- source errors and capability/access blockers

Observability explains what happened; Deployment Editor controls what is allowed.

## Acceptance

- [ ] Owner can enable/disable Discovery per Deployment.
- [ ] Owner can independently allow YouTube/Bilibili where system policy permits.
- [ ] A disabled Deployment schedules no browsing/media/share side effects.
- [ ] Portal can inspect sessions, exposures, decisions, and shares without database access.
- [ ] Discovery owner acceptance can be performed from Portal evidence.

---

# Phase 3 — Conversation Model vNext: Burst Segmentation + Semantic Threads

The current Single Active Topic + continue/switch world model is too restrictive for fast Discord group chat and can self-pollute after a mistaken continuation.

## 3.1 Preserve Burst as a temporal unit

A Conversation Burst is a bounded collection window, not a semantic Topic.

One Burst may contain zero, one, or multiple simultaneous discussion lines.

## 3.2 Conversation Segments

Introduce a segment projection that groups Burst messages using evidence such as:

- explicit replies
- mentions/quotes
- shared media/URL references
- message order/time
- participant exchange
- semantic affinity

A Segment may be:

- topic-bearing discussion
- contextual reply/reaction
- side comment
- media-only/context-only

Assignment to a Thread and contribution to Thread identity must be separate decisions.

Example:

- `哈哈确实` may belong to Thread A but contribute no Thread identity evidence.
- `Topic detection 的问题不是 threshold，而是 single-active assumption` may belong to Thread A and contribute identity evidence.

## 3.3 Semantic Threads

Evolve current Topic semantics toward multiple concurrent Semantic Threads.

A Thread is a durable discussion line that may be hot, warm, dormant, or archived; it is not exclusive with other active Threads.

Do not require creating a new Thread to force the previous Thread into cooling solely because another subject appeared.

Existing Topic tables/contracts may be retained during compatibility migration, but downstream semantics must stop assuming one authoritative active Topic per channel/thread.

## 3.4 Burst-level Conversation Judge

Use deterministic structure first and E5 as candidate retrieval, not final semantic authority.

Target flow:

`Burst -> deterministic interaction structure -> E5 Top-K candidate Threads -> Utility Conversation Judge -> Segments + Thread assignments`

The Judge must return strict structured output and may choose:

- attach to existing Thread
- resume dormant Thread
- create new Thread
- context-only / no Thread identity update

One Judge result should be reusable by Participation, Episode projection, Relationship evidence, Memory, and Discovery.

Simple unambiguous Bursts may fast-path without an LLM call.

## 3.5 Compatibility migration

Current Topic decision observability should be replaced or supplemented with Thread/Segment routing evidence. Do not delete historical Topic/Episode evidence during migration.

## Acceptance

- [ ] One Burst can produce multiple segments assigned to different Threads.
- [ ] Two interleaved reply chains are not forced through alternating Topic switches.
- [ ] Context-only reactions do not broaden Thread semantic identity.
- [ ] A mistaken assignment cannot recursively make the Thread identity broader through every contextual message.
- [ ] Existing perceived Episode constraints remain enforced.

---

# Phase 4 — Participation & Reply Planner on Segments

Character response planning should target a selected Segment/Thread rather than blindly treating the latest message or whole Burst as one subject.

## 4.1 Default behavior

For each Character / Burst:

- rank relevant Segments/Threads;
- select at most one primary target by default;
- decide whether participation pressure is high enough to speak;
- allow silence/reaction when natural.

A single visible Discord message may respond to multiple messages inside the selected Segment.

Do not routinely summarize/respond to every subject in a Burst.

## 4.2 Rare multi-reply

Allow at most two separate replies only for strong independent direct-address cases such as two different direct mentions/replies requiring separate destinations.

## 4.3 Prompt shaping

Roleplay prompt should prefer:

- selected Segment
- bounded room context
- relevant Memory
- bounded Social Context

rather than an unfiltered large recent-message transcript when segmentation is available.

## Acceptance

- [ ] Character can choose the most relevant Thread in a multi-Thread Burst.
- [ ] Character can remain silent despite having a candidate Segment.
- [ ] One response can naturally address multiple messages in one Segment.
- [ ] Multi-reply remains exceptional and bounded.

---

# Phase 5 — Relationship / Social Intelligence v2

The current single `relationship` Learned State behaves primarily like familiarity because ordinary direct interaction always adds positive evidence. It should not represent liking, trust, or comfort by itself.

## 5.1 Dynamic relationship dimensions

Migrate the existing interaction-strength meaning toward `Familiarity` and add directional, Deployment/Server-scoped dimensions:

- Familiarity
- Affinity
- Trust
- Comfort

Ordinary interaction may increase Familiarity but must not automatically increase Affinity/Trust/Comfort.

Dynamic Relationship State belongs to lived Deployment/Server experience.

## 5.2 Canonical Character relationships

Character Cards may define authoritative pre-existing relationships to other Character Cards, including relationship type/description and direction.

Canonical relationship facts:

- do not decay;
- are not overwritten by ordinary runtime learning;
- are author-editable truth.

Examples: partners, siblings, friends, rivals, mentor, coworkers, former friends.

## 5.3 Starting Dynamics / Relationship Prior

Character Creator should provide a Relationship Sheet with:

- target Character
- relationship type
- relationship description
- mutual/directional relationship
- starting dynamics for each direction
- AI-generated suggestions that remain reviewable/editable

Starting Dynamics are a Character Card-level prior/template, not a Server-lived state.

## 5.4 Server initialization

When two related Character Deployments coexist in a Server, Portal may explicitly initialize server-specific dynamic state from the canonical prior.

No second LLM call is required for initialization.

Existing Server-lived state is never silently overwritten when the Character Card prior later changes.

Characters without a canonical relationship use lazy neutral state creation after meaningful social interaction.

## 5.5 Baseline + dynamic delta

For canonical relationships, current relationship dimensions should derive from:

`Canonical baseline + decaying lived delta`

Lived deltas may relax toward the canonical baseline, not toward total stranger/zero by default.

## 5.6 Person Impression

Add a bounded evidence-grounded qualitative model for how a Character sees a person/Character.

Allowed observations must come from real perceived evidence (communication style, repeated interests, interaction preferences, shared experiences). Do not invent hidden psychology or unsupported private traits.

Separate:

- Memory = what I remember about this person;
- Person Impression = how I currently see them;
- Relationship State = how our relationship currently feels.

## 5.7 Social Context prompt injection

Only retrieve social information relevant to the selected Segment/current interaction target.

Compile numeric state into compact natural-language guidance with a hard prompt budget (target approximately 50–120 input tokens per Character turn). Do not inject the whole Social Graph.

## Acceptance

- [ ] Bot↔Human and Bot↔Bot relationships are supported.
- [ ] Bot↔Bot state is directional.
- [ ] Canonical relationship facts survive dynamic conflict/state changes.
- [ ] Frequently arguing does not automatically imply positive Affinity/Trust.
- [ ] Portal can inspect not only scores but also the Character's evidence-grounded impression and shared history.
- [ ] Social Context measurably changes roleplay context without unbounded token growth.

---

# Phase 6 — Integrated observability, regression calibration, and owner acceptance

## Portal / observability

Surface enough evidence to explain:

- Burst segmentation and Thread routing
- Reply Planner target selection
- social state changes and provenance
- provider capability/access state
- structured-output failures/repairs
- Discovery decisions

Avoid presenting derived observations as authoritative raw truth.

## Regression matrix

Include representative cases for:

- rapid Topic/Thread changes inside one Burst
- interleaved reply chains
- short reactions/context-only messages
- malformed but repairable media JSON
- valid vision model with unsupported JSON mode
- text-only model incorrectly configured for media
- quota exhaustion via 429
- quota exhaustion via 400/402/403 error body
- `200 OK` provider error envelope
- billing-required FREE ONLY provider
- resettable free quota
- Bot↔Bot canonical relationship initialization
- negative/neutral social events that should not become positive Affinity

## Final acceptance gate

Before owner review, run batched repository validation appropriate to the changed surfaces, including Python lint/type/tests, web typecheck/tests/build, Discord connector checks, and production/Railway smoke where available.

Do not merge automatically after green validation. Leave the PR open for owner product acceptance.
