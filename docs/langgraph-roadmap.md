# LangGraph Orchestration Roadmap

## Decision

Character Relay will introduce **LangGraph as the orchestration layer** for stateful Character runtime workflows.

Character Relay will **not** adopt the high-level `langchain` agent framework as a runtime dependency. LangGraph may carry its own low-level transitive dependencies, but Character Relay code will continue to own its provider, Tool, retrieval, authority, persistence, and platform abstractions.

The migration rule is:

```text
LangGraph owns orchestration.
Character Relay owns authority.
Existing services own implementation.
```

Tool Calling V2 is the migration baseline, not code to rewrite. Its bounded Tool loop, deployment capability checks, Runtime validation, condition-watch persistence, Character invite safety, Smart Output rules, and Connector continuation limits remain authoritative.

## Architecture boundary

LangGraph may coordinate existing services as nodes/subgraphs:

```text
SocialTurnGraph
├── ParticipationNode
├── CharacterTurnSubgraph
│   ├── ContextNode
│   ├── KnowledgeNode
│   ├── CharacterModelNode
│   ├── ToolExecutionNode -> existing ToolRuntime
│   ├── SmartOutputNode
│   └── AuthorityNode
├── InviteNode
└── DeliveryNode

ConditionWatchGraph
├── WatchValidationNode
├── WatchEvaluationNode -> existing provider + read-only ToolRuntime
├── WatchDecisionNode
└── WatchTransitionNode -> existing repositories / scheduler
```

The following remain outside LangGraph implementation ownership:

- `ToolRuntime` and Tool Registry;
- provider adapters and credential handling;
- Context Layer and RAG implementation;
- Smart Participation scoring logic;
- Smart Output parsing/validation;
- Browser Capability;
- business repositories and SQLite records;
- Scheduler/Condition Watch polling clocks;
- Discord Gateway/Webhook lifecycle and future platform connectors.

Graph checkpoints, when introduced, represent **workflow execution state**. Character Relay repositories remain **business truth**.

## Node categories

Runtime Trace Explorer will classify nodes consistently:

- `decision` — routing/participant selection/conditional edges;
- `context` — recent context, RAG, and other prompt preparation;
- `agentic` — Character/provider model decisions;
- `capability` — ToolRuntime or another external capability;
- `authority` — Character Relay validation that decides what is legal/executable;
- `state` — authoritative product-state transition through repositories;
- `side_effect` — platform delivery or another externally visible action.

A service should become its own node when it changes workflow state, chooses an edge, calls a model, crosses an authority boundary, or performs an externally visible side effect. Internal implementation details should remain inside the existing service rather than being exploded into tiny graph nodes.

## Phase 1 — State + Node + Trace Foundation 🚧

Goal: introduce LangGraph contracts in **shadow mode with zero production behavior change**.

Deliverables:

- add the `langgraph` package without adding the high-level `langchain` package;
- add `CHARACTER_RELAY_LANGGRAPH_ENABLED=false` as the default migration flag;
- add `CharacterRuntimeState` for privacy-safe workflow coordination;
- add run-scoped `OrchestrationRuntimeContext` for dependencies/configuration;
- add the privacy-safe `RuntimeTraceEvent` / `RuntimeTraceSink` contract;
- define node categories used by the future Runtime Trace Explorer;
- compile and execute a no-side-effect foundation graph in tests;
- keep Discord, Tool Calling V2, RAG, Smart Participation, Scheduler, and Condition Watch production traffic on the existing runtime.

Exit gate:

```text
existing runtime behavior unchanged
+ foundation graph compiles/runs
+ feature flag defaults disabled
+ trace contract tested
+ existing CI remains green
```

## Phase 2 — Condition Watch Graph Pilot

Goal: use the completed Tool Calling V2 Condition Watch workflow as the first parity-tested production-shaped graph.

Keep `ConditionWatchService` responsible for the clock and `claim_due()` polling. Route **one claimed watch evaluation** through `ConditionWatchGraph`:

```text
ConditionWatchService
→ claim_due
→ ConditionWatchGraph
   → validate watch/deployment
   → resolve read-only assigned Tools
   → evaluate fresh evidence
   → repair invalid control output when bounded policy allows
   → decide triggered / not met / failed
   → persist through existing repositories
→ existing Scheduler notification path
```

Migration approach:

1. run old evaluator as baseline fixtures;
2. run graph evaluator against the same fixtures;
3. compare decisions, Tool availability, repository transitions, and failure behavior;
4. enable graph path only after parity is demonstrated.

The graph must not become the scheduling clock and must not replace Condition Watch business records.

## Phase 3 — Character Turn Graph

Goal: make one Character turn the reusable runtime subgraph.

Target flow:

```text
Resolve Deployment
→ ContextNode
→ KnowledgeNode
→ CharacterModelNode
→ ToolExecutionNode (existing bounded ToolRuntime)
→ CharacterModelNode when Tool result requires continuation
→ SmartOutputNode
→ AuthorityNode
→ platform command result
```

Migration order:

1. Test Room / direct Runtime tester;
2. shadow comparison against the existing Character path;
3. selected internal Discord deployment;
4. broader Discord cutover after parity.

The existing `max_tool_rounds=2`, one-side-effect-per-turn rule, deployment Tool allowlist, network safety, destination scope, and execution-integrity rules remain unchanged.

## Phase 4 — Social Turn Graph

Goal: move multi-character orchestration above reusable `CharacterTurnSubgraph` instances.

Target flow:

```text
Normalized Platform Event
→ ParticipationNode
→ ordered participant set
→ CharacterTurnSubgraph(A)
→ InviteNode / continuation decision
→ Character Relay Runtime validation
→ optional participant expansion
→ CharacterTurnSubgraph(B)
→ DeliveryNode(s)
```

`character.invite` remains a proposal. LangGraph follows only a Runtime-validated transition; it does not decide by itself whether another Character is authorized to participate.

During this phase, Discord Connector orchestration should become thinner over time while retaining transport concerns such as Gateway connection, deduplication, heartbeat, webhook/Bot delivery, and platform-specific rendering.

Exit gate:

- Smart Participation parity;
- ordered multi-character context parity;
- invite/continuation bounds preserved;
- no recursive invite trees;
- unique-turn/depth/response-budget protections preserved;
- Runtime Trace Explorer can explain why every participant entered the turn.

## Phase 5 — Durable Runtime + Runtime Trace Explorer + Cutover

Goal: add recovery/observability after graph boundaries have proved stable.

Durable execution work:

- add checkpointer support only where workflow recovery is useful;
- keep graph checkpoint storage separate in responsibility from Character Relay business records;
- add operation IDs/idempotency for externally visible side effects;
- support safe resume/replay without duplicate Discord messages, reminders, polls, or future notifications;
- retire only orchestration glue that has become demonstrably redundant.

### Runtime Trace Explorer

The product visualization should trace the Character Relay runtime, not merely display a generic LangGraph diagram.

One trace should show:

```text
trace / graph run
→ node start
→ privacy-safe state-key diff
→ Runtime Authority result
→ model / RAG / Tool classification
→ authoritative repository transition
→ platform side effect
```

Example social trace:

```text
ParticipationNode
  selected: Mia

CharacterTurn(Mia)
  ContextNode -> ready
  KnowledgeNode -> 3 chunks selected
  CharacterModelNode -> character.invite proposal p1
  ToolExecutionNode -> proposal pending Runtime validation

InviteNode
  p1 -> Serena
  authority -> accepted
  participants: [Mia] -> [Mia, Serena]

CharacterTurn(Serena)
  CharacterModelNode -> Smart Output
  AuthorityNode -> accepted

DeliveryNode
  Discord -> delivered
```

Trace storage must not contain raw provider credentials, authorization headers, full private prompts, raw RAG excerpts, raw Tool arguments/results, or other secret/private payloads merely to make visualization easier. Existing Provider Trace can remain the provider-call diagnostic view; Runtime Trace Explorer should focus on orchestration and state transitions and may link to Provider Trace records by safe IDs.

## Deferred / optional evaluation

After Phase 5, reevaluate whether selected low-level integration adapters would reduce maintenance cost. Do not introduce the high-level LangChain agent runtime unless it solves a measured problem without creating a second authority/tool/retrieval abstraction.

Potential later workflows that can build on this foundation:

- long-term Character Memory and memory consolidation;
- relationship state;
- human approval / interrupt flows for higher-risk actions;
- multi-platform social turns;
- longer-lived Character tasks;
- richer evaluation graphs that compare production and Echo Masque execution paths.
