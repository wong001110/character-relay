# Conversation Intelligence Architecture

Status: **historical design proposal — superseded by Intelligence Core v3 where they conflict**

> Preserve this document for decision history. Do not implement Topic-centric authority or infer current behavior from it. Use `docs/intelligence-core-v3-architecture.md` and current source/tests.

This document records the current architecture decisions and open questions for the next Character Relay conversation-intelligence refactor. It is intentionally documentation-only. It does not change Runtime behavior.

## 1. Motivation

The current system has grown several independent decision layers that can overlap:

- Smart Participation decides which deployed characters should participate.
- Smart Output still allows a selected Character model to return `ignore`.
- Media understanding is partly Runtime-owned and partly delegated to Character Tool Calling.
- Topic continuity, Memory retrieval/writes, Wiki derivation, Conversation Graph, and Character context routing are separate systems with partially overlapping responsibilities.
- Utility models are increasingly used for judgment, but the Utility pool should not be treated as a pool of necessarily small models. Free/resettable quota can include capable large models.

The goal is to make the responsibility boundary explicit so that:

1. Roleplay API tokens are spent on persona behavior and language generation rather than infrastructure decisions.
2. Runtime decisions have one authoritative owner instead of being repeated by multiple LLM calls.
3. Media-dependent turns do not allow a Character to confidently answer unseen content when the answer requires that content.
4. Topic, Memory, Wiki, Episode, and Media are distinct concepts rather than one evolving summary object.
5. LLMs receive fixed structured candidates and produce fixed structured decisions instead of guessing IDs, scopes, state, or allowed actions.
6. Internal cognitive retrieval can be automatic while preserving limited Character-driven exploration when useful.

---

## 2. Core architecture principle

Character Relay should separate four responsibilities:

```text
1. Participation Runtime
   Who is allowed / expected to speak?

2. Context & Evidence Runtime
   What information is required before that Character can respond?

3. Character LLM
   Given the authorized turn and grounded context, how does this Character respond?

4. Persistence & Consolidation
   What from this turn should become durable Topic state, Memory, Wiki knowledge, or Graph evidence?
```

The primary principle is:

> LLMs decide semantic intent inside a bounded contract. Runtime owns authority, identity, scope, validation, provenance, lifecycle, and side effects.

A second principle is:

> The Roleplay LLM should not be the default implementation of Character Relay infrastructure.

The Character model should primarily answer:

- Who am I?
- What do I think about this?
- What social action or wording fits my persona?

Conversation Intelligence should answer:

- What Topic is this?
- Is this a current Topic, a resumed historical Topic, or a new Topic?
- What Memory, Wiki, conversation history, or Media evidence is required?
- Which Character(s) should participate?

Runtime should answer:

- Which candidates are valid?
- Which scopes may be searched?
- Which actions are legal?
- Which tools are available?
- Which writes are permitted?
- What data was actually perceived or retrieved?

---

## 3. Participation Authority: remove duplicate "should I speak?" decisions

### 3.1 Current problem

Smart Participation V4 can already return an authoritative speaker plan. The Connector then builds the actual selected audience from that plan.

However, the selected Character still receives Smart Output actions that include:

```text
ignore | message | react | sticker
```

This creates a duplicate decision path:

```text
Speaker resolver selects Ann
        -> Roleplay API is called
        -> Ann decides "ignore"
        -> no visible output
        -> user Roleplay tokens were spent for nothing
```

### 3.2 Proposed rule: Single Participation Authority

When `speaker_plan_authoritative = true`, the Roleplay LLM must not independently re-decide whether it participates.

Suggested turn contract:

```json
{
  "participation_authority": "runtime",
  "must_respond": true,
  "turn_role": "primary"
}
```

Suggested action constraints:

| Turn state | Character model invocation | Allowed social actions |
|---|---:|---|
| Not selected | No | none |
| Primary selected | Yes | `message` initially; possibly a separately approved contract later |
| Secondary selected | Yes | `message`, `react`, `sticker` depending on final design |
| Non-Smart / explicitly addressed path | Existing behavior may remain | context-dependent |

Important: do not remove `ignore` globally until all non-authoritative participation paths are reviewed. Instead, make available actions turn-contract-specific.

### 3.3 Failure must not masquerade as ignore

These are different states and should remain distinct in traces/contracts:

```text
character chose silence
provider failed
runtime aborted
output schema invalid
speaker was not selected
```

A provider error must not be represented as if the Character voluntarily chose `ignore`.

---

## 4. Media: distinguish attention from epistemic dependency

### 4.1 Current behavior

The current Runtime already treats visible image attachments differently from links/videos:

- Visible image attachments are passively perceived when analysis is available.
- Links, videos, and other non-visible shared content are exposed to the Character through `media.inspect`.
- The Character may answer without calling `media.inspect`.

Therefore, "the bot sometimes speaks without looking at media" is not only a threshold problem. It is allowed by the current design.

### 4.2 New concept: Media Dependency

Whether a Character *likes* or *wants* to inspect something is a persona decision.

Whether a valid answer *requires knowledge of the content* is a Runtime epistemic decision.

Define:

```text
REQUIRED
OPTIONAL
NONE
```

Examples:

| Turn | Dependency | Expected behavior |
|---|---|---|
| "这个视频里面谁是反派？" + video | REQUIRED | Resolve content before final answer |
| Only a video/link, where the media itself is the conversation subject | usually REQUIRED for speaker/context planning | Resolve enough objective content before selecting/responding |
| "这个视频笑死我了" + video | OPTIONAL | Character may inspect or respond from visible context |
| A link is incidental to another active discussion | OPTIONAL/NONE | Do not force inspection |
| Visible image attachment | PASSIVE perception path | Keep current passive semantics |

### 4.3 Required media should be Runtime-owned

For REQUIRED media:

```text
Incoming Turn
   -> Media Dependency Gate
   -> resolve objective Media understanding
   -> Context / Speaker planning
   -> Character LLM
```

It should not be:

```text
Character LLM
   -> maybe calls media.inspect
   -> maybe answers without it
```

### 4.4 Optional media remains Character-driven

For OPTIONAL media, `media.inspect` remains useful as a Character exploration tool.

This preserves persona-specific curiosity without making correctness depend on that curiosity.

### 4.5 Analyze once, perceive per Character

Objective Media understanding should be reusable:

```text
one Media object
   -> one objective analysis/cache entry
   -> reused by multiple Characters
```

Character-specific state remains separate:

```text
objective analysis: what the media contains
perception state: whether Ann actually perceived it this turn
persona reaction: what Ann cares about / says about it
```

This avoids repeated Vision/transcript/fetch work for identical content while keeping epistemic provenance accurate.

### 4.6 Link previews are not inspected content

Discord embed metadata, page title, provider name, and URL transport text are preview evidence only.

They must not be treated as equivalent to actual inspected content.

---

## 5. Utility model pool: treat it as an Intelligence Pool, not a "small-model pool"

Character Relay may use free/resettable quotas from providers. Those free models are not necessarily small; some may be large and capable.

Use the conceptual split:

```text
Roleplay LLM
= Persona Model
= user-selected / user-funded
= final character behavior and wording

Utility Intelligence Pool
= Character Relay cognitive/infrastructure models
= free/resettable quota preferred
= model size/capability may vary
= planning, judging, consolidation, structured semantic decisions
```

The important constraint is not model size. It is availability volatility:

- quota may reset,
- model may disappear,
- provider may return 429,
- a large free model today may be replaced by a weaker fallback tomorrow.

Therefore every Utility LLM path must have a bounded deterministic fallback or a safe degraded mode.

---

## 6. Conversation Intelligence pipeline

Do not call separate LLM judges for every subsystem when one bounded plan can resolve multiple gray-zone decisions.

Recommended flow:

```text
Incoming burst
   |
   v
Deterministic preflight / candidate retrieval
   - explicit reply/reference signals
   - current Topic
   - embedding candidates
   - recent Episodes
   - relevant Memory candidates
   - Wiki candidates
   - unresolved Media descriptors
   - eligible speaker candidates
   |
   v
Utility Conversation Intelligence
   - choose among supplied candidates
   - classify context needs
   - resolve gray-zone Topic/Speaker/Media requirements
   |
   v
Runtime validation + execution
   - retrieve selected context
   - force required Media resolution
   - validate scopes/IDs/lifecycle
   |
   v
Character Turn Contract
   |
   v
Roleplay LLM
   - usually one final call
   - optional Internal Tool escape hatch when deeper exploration is genuinely needed
```

Embedding is primarily candidate retrieval, not the final authority for every semantic decision.

---

## 7. Structured input/output is mandatory

### 7.1 No free-form infrastructure decisions

The Utility LLM must not receive prose such as:

> "There may be some old Topic and Memory; decide what to use."

Runtime supplies explicit candidates with local references.

Example input shape:

```json
{
  "schema_version": "conversation_plan.v1",
  "request_id": "ctxreq_123",
  "turn": {
    "burst_ref": "burst_1",
    "messages": [
      {
        "ref": "msg_1",
        "author_ref": "user_1",
        "text": "之前那个绝区零的反派到底是谁？"
      }
    ]
  },
  "current_topic": {
    "ref": "topic_current",
    "label": "绝区零剧情讨论",
    "age_seconds": 420
  },
  "topic_candidates": [
    {
      "ref": "topic_1",
      "label": "绝区零剧情讨论",
      "retrieval_score": 0.82
    }
  ],
  "memory_candidates": [
    {
      "ref": "memory_1",
      "memory_type": "preference",
      "content": "user_1 喜欢角色雅",
      "retrieval_score": 0.77
    }
  ],
  "media_candidates": [
    {
      "ref": "media_1",
      "kind": "video",
      "state": "unresolved"
    }
  ],
  "speaker_candidates": [
    {
      "ref": "deployment_ann",
      "display_name": "Ann",
      "relevance_score": 0.81
    }
  ]
}
```

Example output shape:

```json
{
  "schema_version": "conversation_plan.v1",
  "request_id": "ctxreq_123",
  "topic": {
    "action": "resume",
    "topic_ref": "topic_1",
    "confidence": 0.91
  },
  "context_plan": {
    "memory_refs": ["memory_1"],
    "wiki_refs": [],
    "conversation_search": null,
    "media": {
      "dependency": "required",
      "media_refs": ["media_1"]
    }
  },
  "speaker_plan": [
    {
      "deployment_ref": "deployment_ann",
      "role": "primary"
    }
  ]
}
```

Fixed enums should be used where possible, for example:

```text
topic.action = continue | resume | new | uncertain
media.dependency = required | optional | none
speaker.role = primary | secondary
```

### 7.2 Refs are prompt-local capabilities

The LLM may choose only supplied refs.

It may not invent:

- Topic IDs,
- Memory IDs,
- Deployment IDs,
- Server/channel scope,
- user ownership,
- database keys,
- security/visibility boundaries.

### 7.3 Runtime validates even valid JSON

Schema validation alone is not authority.

Runtime must still verify:

- referenced candidate exists,
- reference belongs to this request/candidate set,
- owner/scope is valid,
- lifecycle/status permits the operation,
- requested action is allowed,
- required evidence exists,
- write authority is satisfied.

### 7.4 Version every contract

All AI-facing structured contracts should carry explicit versions:

```text
conversation_plan.v1
character_turn.v1
memory_search.v1
topic_resolve.v1
media_dependency.v1
speaker_plan.v1
```

Do not depend on prompt prose to make old/new schemas "approximately compatible".

---

## 8. Character Turn Contract

The Roleplay LLM should receive already-authorized context rather than raw infrastructure state.

Illustrative shape:

```json
{
  "schema_version": "character_turn.v1",
  "turn_contract": {
    "participation_authority": "runtime",
    "must_respond": true,
    "role": "primary"
  },
  "conversation": {
    "topic": "绝区零剧情讨论",
    "messages": []
  },
  "context": {
    "memories": [],
    "wiki": [],
    "media_observations": []
  },
  "available_actions": ["message"],
  "available_internal_tools": [
    "memory.search",
    "conversation.search"
  ]
}
```

If the current contract says Primary must respond, `ignore` should not merely be discouraged in the prompt; it should be absent from the current action schema.

---

## 9. Tool taxonomy

### 9.1 Internal Context Tools

These are Character Relay cognitive/context tools and should generally exist automatically rather than requiring user assignment:

```text
memory.search
topic.search
wiki.lookup
conversation.search
entity.lookup (future)
media.inspect (special Runtime Context Tool)
```

Properties:

- Runtime injects owner/Character/deployment/server/user scope.
- LLM supplies semantic intent only.
- Read-only by default.
- No raw DB IDs, SQL, vectors, or unrestricted scope parameters.

Example:

```json
{
  "schema_version": "memory_search.v1",
  "query": "之前关于雅的讨论",
  "memory_types": ["preference", "relationship", "episode"],
  "limit": 5
}
```

The model should not be allowed to provide `owner_id`, arbitrary `guild_id`, arbitrary `character_card_id`, or visibility controls.

### 9.2 External Capability Tools

These are optional capabilities exposed by deployment/user configuration:

```text
web.search
web.fetch
weather.get
places.search
image.search
image.generate
scheduler.remind
discord.create_poll
...
```

They may require external APIs, credentials, side-effect policy, quotas, or explicit deployment assignment.

### 9.3 Runtime-required operations are not Character tools

These should not be disguised as optional Tool Calling:

```text
required Media resolution
speaker admission/selection
Topic lifecycle validation
scope/permission validation
rate limits/cooldowns
provider-failure classification
```

They are Runtime responsibilities.

---

## 10. Who decides Internal Context retrieval?

Use a hybrid model.

### 10.1 Default: Runtime / Utility Intelligence

Most context retrieval should be decided before the Roleplay LLM call:

- Active Topic
- relevant Memory
- relevant Wiki knowledge
- explicit historical reference
- REQUIRED Media
- historical Topic resume candidates
- bounded relevant conversation history

The Roleplay LLM should normally receive the resulting Context Package and respond once.

### 10.2 Character Internal Tools as an escape hatch

The Character may still perform deeper Internal retrieval when its persona-specific thought process creates a need the planner could not know in advance.

Examples:

```text
memory.search
conversation.search
topic.search
wiki.lookup
media.inspect (OPTIONAL media only)
```

This should be exceptional rather than the primary retrieval path.

Conceptually:

```text
most turns: Utility/Runtime context -> one Roleplay call
rare turns: Utility/Runtime context -> Roleplay -> Internal Tool -> Roleplay continuation
```

The exact percentage is not an API contract and should be measured rather than hard-coded.

---

## 11. Topic, Episode, Memory, Wiki, Media: separate the data model

Do not use one mutable Topic capsule as a substitute for all long-term cognition.

Recommended conceptual layers:

| Layer | Meaning | Authority/provenance |
|---|---|---|
| Episode | What actually happened in a bounded conversation/event | Source/provenance record |
| Topic | Organizational grouping: what a set of Episodes is about | Derived organizer |
| Memory | Durable character/user/relationship/event knowledge derived from evidence | Fallible, versionable, supersedable |
| Wiki | Consolidated higher-level understanding over many sources | Derived, source-backed, staleable |
| Media Object | Shared image/video/link plus objective analysis and provenance | Source evidence + derived analysis |
| Entity/Graph | People/characters/concepts/relations connecting the above | Structural index, optional/future authority rules |

Illustrative relationships:

```text
Message
   |
   v
Episode -----------> Media Object
   |                     |
   | ABOUT               | ABOUT
   v                     v
Topic ---------------> Entity
   |                     ^
   | source              |
   v                     |
Memory -----------------+
   |
   v
Wiki / higher-level consolidated knowledge
```

---

## 12. Topic design

Topic should primarily organize Episodes and support conversational continuity.

It should not be the canonical store for:

- durable user preferences,
- relationship facts,
- all long-term history,
- Wiki-level knowledge.

### 12.1 Target resolver

Move toward:

```text
CURRENT
RESUME historical Topic
NEW Topic
```

Candidate retrieval may use embeddings/sparse/entity/recency evidence, with Utility Intelligence adjudicating ambiguous candidate margins.

### 12.2 Stable identity vs rolling state

Keep separate concepts:

```text
TopicIdentity
- stable label/subject/entity anchors

TopicState
- recent summary
- current participants
- open loops
- pending actions
- recent Episodes
```

Rolling context must not redefine Topic identity through positive-feedback drift.

### 12.3 URL-only content is not Topic evidence

A URL is transport, not semantic identity.

Until content is actually inspected/resolved:

- do not invent a Topic from the URL,
- do not allow common URL/domain tokens to create similarity,
- preview metadata is not equivalent to inspected content.

This topic-drift/link behavior is being handled separately from this design PR and should not be reimplemented here.

---

## 13. Memory design

### 13.1 Retrieval and writes have different authority

Read/retrieval:

```text
Runtime/Utility prefetch by default
Character can optionally deep-search
```

Writes:

```text
Character may propose
Utility/Memory Intelligence recommends bounded action
Runtime validates and commits
```

Suggested bounded write actions:

```text
IGNORE
CREATE
REINFORCE
MERGE
SUPERSEDE
```

Roleplay LLM should not directly mutate Memory rows.

### 13.2 Scope must be type-aware

Do not force every durable Memory to be channel/thread-local.

Potential scopes:

```text
Character <-> User
Character <-> Server
Character <-> Channel
Topic-local
shared/global knowledge where explicitly allowed
```

Examples:

- "Alice likes Miyabi" should usually survive moving from `#general` to `#games` for the same Character/User relationship.
- "This channel is currently organizing event X" may be channel-scoped.
- "During Topic X, Alice claimed Y" may remain Topic/Episode-scoped unless consolidated.

### 13.3 Retrieval should be type-aware

Future Memory ranking may consider:

```text
semantic relevance
recency
importance
confidence
relationship proximity
temporal validity
use frequency
```

But weighting must depend on Memory type. Stable identity/preference facts should not decay exactly like transient episodic context.

### 13.4 Prefer consolidation over "every message becomes Memory"

Conversation messages/Episodes are evidence.

Only selected information should become durable Memory.

Longer-term flow:

```text
Episodes
   -> important/repeated facts
   -> Memory
   -> related Memories/Episodes
   -> Reflection / Wiki-level understanding
```

---

## 14. Wiki / LLM Wiki design

Current Knowledge Wiki direction already uses the correct principle:

> Raw source knowledge remains authoritative; Wiki pages are derived and can become stale.

Keep this property.

Future Wiki should grow beyond one overview page into source-backed Entity/Topic pages and higher-level consolidation.

Potential hierarchy:

```text
Raw Knowledge / Episodes / Memories
   -> Entities / relationships
   -> Topic or Entity pages
   -> higher-level summaries / communities
```

Wiki should always retain provenance/source manifests and staleness rules. It must not silently overwrite raw evidence.

References discussed during design exploration include:

- ChatGPT Saved Memory + Reference Chat History product behavior
- LangGraph/LangChain short-term vs long-term memory
- Generative Agents: memory stream, relevance/recency/importance, reflection
- Letta: core memory vs archival memory and agent-triggered retrieval
- Zep/Graphiti: Episodes, entities/relations, temporal validity and provenance
- Microsoft GraphRAG: entity/relationship graph and community summaries
- RAPTOR: hierarchical clustered summaries
- CoALA: modular agent memory/action architecture

These references are conceptual inputs, not requirements to reproduce another system verbatim.

---

## 15. Consolidation should be off the critical Roleplay path where possible

Not every durable cognition update needs to happen before the Discord reply.

Recommended split:

### Hot path

Only operations required for the current answer:

- Topic resolution required for current context
- Memory/Wiki retrieval
- REQUIRED Media resolution
- speaker plan
- Character response

### Post-turn / asynchronous consolidation

Where safe:

- Memory candidate evaluation/write
- Topic capsule/state update
- Topic merge/relabel suggestions
- Wiki refresh/consolidation
- Graph projection
- learned state/evidence updates

This reduces latency and avoids consuming the Roleplay model for bookkeeping.

---

## 16. Proposed end-to-end turn flow

```text
Incoming Discord event / burst
        |
        v
[Ingress + deterministic preflight]
        |
        +-- explicit mentions/replies
        +-- recent context
        +-- eligible deployments
        +-- Topic candidates
        +-- Memory candidates
        +-- Wiki candidates
        +-- Media descriptors
        |
        v
[Utility Conversation Intelligence]
        |
        +-- Topic: CURRENT / RESUME / NEW
        +-- Context needs
        +-- Media dependency
        +-- Speaker plan
        |
        v
[Runtime validation]
        |
        +-- validate refs/scopes/lifecycle
        +-- execute required internal retrieval
        +-- resolve REQUIRED Media
        |
        v
[Character Turn Contract]
        |
        +-- authoritative participation
        +-- grounded context
        +-- turn-specific action schema
        +-- limited Internal Tools
        |
        v
[Roleplay LLM]
        |
        +-- direct final social action (common)
        |
        +-- optional Internal Tool exploration (exception)
        |       |
        |       v
        |   validated Internal retrieval
        |       |
        +-------+
        |
        v
[Runtime authorization + Discord execution]
        |
        v
[Post-turn consolidation]
        +-- Episode/provenance
        +-- Topic state
        +-- Memory proposal/write
        +-- Wiki/Graph/learned-state projection
```

---

## 17. Proposed implementation sequence

This PR does **not** authorize implementation yet. The following is the proposed order once contracts are approved.

### Phase A - Participation Authority

- Introduce explicit turn participation authority/role.
- When V4 speaker plan is authoritative, do not permit a Primary Roleplay response to resolve to voluntary `ignore`.
- Separate provider/runtime failure from Character silence.
- Add traces that distinguish not-selected, selected/responded, selected/tool-expanded, provider-failed, schema-failed.

### Phase B - Media Dependency

- Introduce `required | optional | none` dependency contract.
- Preserve passive visible-image perception.
- Resolve REQUIRED non-visible media before final Character response.
- Decide whether media-only turns need objective understanding before speaker selection.
- Reuse objective Media analysis across Characters while tracking per-Character perception separately.

### Phase C - Conversation Planning Contract

- Define versioned `conversation_plan.v1` input/output schemas.
- Deterministic candidate generation first.
- Utility Intelligence chooses only supplied refs/enums.
- Runtime validates all decisions.
- Add deterministic fallback when Utility pool is unavailable.

### Phase D - Topic Resolver

- Separate Topic identity from rolling state.
- Add CURRENT / RESUME / NEW historical candidate resolution.
- Keep URL-only/uninspected content out of Topic identity.
- Move toward Episode-backed Topic organization.

### Phase E - Memory scopes and consolidation

- Define type-aware scopes.
- Keep Utility recommendations bounded to ignore/create/reinforce/merge/supersede.
- Add post-turn consolidation where practical.
- Make retrieval scoring type-aware.

### Phase F - Internal Context Tools

- Add/read-contract for `memory.search`, `topic.search`, `conversation.search`, `wiki.lookup`.
- Runtime injects all authority/scope parameters.
- Internal tools are automatic platform capabilities rather than user-assigned external tools.
- Keep Character-driven Internal calls as a bounded escape hatch, not the primary retrieval path.

### Phase G - Wiki / Graph consolidation

- Expand source-backed Wiki beyond a single overview.
- Connect Episode/Topic/Memory/Entity provenance.
- Evaluate hierarchical/community consolidation only after correctness and provenance are stable.

---

## 18. Decisions currently considered agreed direction

The following points reflect the current discussion and should be treated as the working direction unless changed explicitly:

1. Smart Participation and Character generation must not independently re-decide the same participation choice.
2. Roleplay LLM tokens should primarily be spent on persona response, not platform bookkeeping/judging.
3. Utility free-token models may be large/capable; call the resource an Intelligence Pool rather than assuming "small judge models".
4. Utility LLM availability is volatile, so deterministic fallback remains mandatory.
5. Context planning should usually occur before the Roleplay LLM call.
6. Character-driven Internal Tool Calling remains available only as bounded extra exploration.
7. Internal Context Tools and External Capability Tools are separate categories.
8. Runtime-required operations are not optional Character tools.
9. Structured input and output contracts are mandatory; LLMs must not invent refs, scopes, IDs, or actions.
10. Runtime remains authority after LLM/schema validation.
11. REQUIRED media understanding is Runtime-owned; OPTIONAL media may remain Character-driven.
12. Objective Media understanding should be reusable while per-Character perception remains explicit.
13. Topic, Episode, Memory, Wiki, and Media are distinct concepts.
14. Topic is an organizer, not the durable-memory truth store.
15. Memory writes remain proposed/judged/validated rather than directly committed by the Roleplay LLM.
16. Wiki is derived from authoritative evidence and must preserve provenance/staleness.
17. Consolidation should move off the critical response path when it is not required for the current reply.

---

## 19. Open questions to decide before implementation

These points remain intentionally open:

1. **Primary action contract:** Should authoritative Primary always require `message`, or are `react`/`sticker` ever valid Primary outcomes?
2. **Secondary contract:** Which actions may a Secondary participant use, and can a Secondary ever become silent after selection?
3. **Media-only turns:** Should unresolved media always be analyzed before speaker selection, or only when no usable text/preview evidence exists?
4. **Media dependency owner:** Can deterministic rules resolve most `required/optional/none`, with Utility only for gray zones, or should Utility return this as part of every Conversation Plan?
5. **Conversation-plan granularity:** One Utility plan per message or per collected burst?
6. **Planner responsibilities:** Should speaker planning remain a separate V4 stage initially, or be merged into `conversation_plan.v1` once parity is proven?
7. **Memory scope migration:** How should existing channel/thread-scoped memories migrate to relationship/server-level scopes?
8. **Episode storage:** Reuse existing transcript/message persistence, add an explicit Episode table, or project Episodes from existing records?
9. **Internal Tool budget:** Maximum number of Roleplay-driven Internal Tool rounds per turn.
10. **Wiki sources:** Whether Character/relationship Memories may feed shared Wiki pages, and under what visibility/privacy boundary.
11. **Graph authority:** Which graph edges are merely derived indexes versus durable temporal facts.
12. **Background consolidation trigger:** time-based, Topic cooling/closing, message-count threshold, or a hybrid.

These should be resolved in design review before implementation phases begin.

---

## 20. Non-goals of this documentation PR

This PR does not:

- change Smart Participation behavior,
- remove `ignore`,
- modify Media inspection behavior,
- modify Topic thresholds or lifecycle,
- implement historical Topic resume,
- change Memory scope/storage,
- add Internal Tools,
- change Wiki generation,
- merge or replace the separate Topic drift fix,
- merge any existing PR.

It exists to establish the architecture contract before further runtime changes.
