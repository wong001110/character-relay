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

## Environment namespace

Character Relay application settings use the `CHARACTER_RELAY_*` environment namespace. The orchestration migration does not introduce a second configuration namespace.

## Rollout controls

LangGraph production rollout uses one master kill switch plus workflow-specific switches:

```text
CHARACTER_RELAY_LANGGRAPH_ENABLED=false
CHARACTER_RELAY_LANGGRAPH_CONDITION_WATCH_ENABLED=false
CHARACTER_RELAY_LANGGRAPH_CHARACTER_TURN_ENABLED=false
CHARACTER_RELAY_LANGGRAPH_SOCIAL_TURN_ENABLED=false
```

The master switch never enables a workflow by itself. A workflow uses LangGraph only when both the master switch and its workflow switch are enabled. This keeps rollout and rollback independent as new graphs arrive:

```text
Phase 2 pilot
LANGGRAPH_ENABLED=true
LANGGRAPH_CONDITION_WATCH_ENABLED=true
LANGGRAPH_CHARACTER_TURN_ENABLED=false
LANGGRAPH_SOCIAL_TURN_ENABLED=false

Phase 3 pilot
LANGGRAPH_ENABLED=true
LANGGRAPH_CONDITION_WATCH_ENABLED=true
LANGGRAPH_CHARACTER_TURN_ENABLED=true
LANGGRAPH_SOCIAL_TURN_ENABLED=false

Phase 4 pilot
LANGGRAPH_ENABLED=true
LANGGRAPH_CONDITION_WATCH_ENABLED=true
LANGGRAPH_CHARACTER_TURN_ENABLED=true
LANGGRAPH_SOCIAL_TURN_ENABLED=true
```

Setting `CHARACTER_RELAY_LANGGRAPH_ENABLED=false` is the global rollback path and disables all LangGraph workflow routing regardless of the workflow-specific values.

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
├── WatchEvaluationNode -> existing ConditionWatchEvaluatorRuntime
├── WatchDecision edge
├── WatchNotificationNode -> existing notifier / Scheduler path
└── WatchTransitionNode -> existing ConditionWatchRepository
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

## Phase 1 — State + Node + Trace Foundation ✅

Goal: introduce LangGraph contracts in **shadow mode with zero production behavior change**.

Completed:

- added the `langgraph` package without adding the high-level `langchain` package;
- added `CHARACTER_RELAY_LANGGRAPH_ENABLED=false` as the master migration flag;
- added `CharacterRuntimeState` for privacy-safe workflow coordination;
- added run-scoped `OrchestrationRuntimeContext` for dependencies/configuration;
- added the privacy-safe `RuntimeTraceEvent` / `RuntimeTraceSink` contract;
- defined node categories used by the future Runtime Trace Explorer;
- compiled and executed a no-side-effect foundation graph in tests;
- kept Discord, Tool Calling V2, RAG, Smart Participation, Scheduler, and Condition Watch production traffic on the existing runtime.

Exit gate passed:

```text
existing runtime behavior unchanged
+ foundation graph compiles/runs
+ feature flag defaults disabled
+ trace contract tested
+ CI green before merge
```

Phase 1 merged through PR #122.

## Phase 2 — Condition Watch Graph Pilot 🚧

Goal: use the completed Tool Calling V2 Condition Watch workflow as the first parity-tested production-shaped graph.

`ConditionWatchService` remains responsible for the clock and `claim_due()` polling. Only **one already-claimed watch attempt** is handed to `ConditionWatchGraph` when both `CHARACTER_RELAY_LANGGRAPH_ENABLED=true` and `CHARACTER_RELAY_LANGGRAPH_CONDITION_WATCH_ENABLED=true`:

```text
ConditionWatchService
→ claim_due
→ ConditionWatchGraph
   → WatchEvaluationNode
      -> existing ConditionWatchEvaluatorRuntime
         -> deployment/Character validation
         -> assigned read-only Tool resolution
         -> bounded provider + ToolRuntime evaluation
         -> one bounded control-output repair
   → conditional edge
      ├─ not met -> existing repository mark_not_met
      ├─ triggered -> existing notifier -> repository mark_triggered
      └─ failed -> existing repository mark_failure
→ existing Scheduler delivery path
```

The initial Phase 2 node boundary is intentionally coarse. `ConditionWatchEvaluatorRuntime` remains one service boundary rather than splitting provider calls, ToolRuntime checks, and repair logic into new graph nodes. This preserves the Phase 1 rule that a LangGraph node wraps an existing service boundary instead of rewriting stable Runtime internals.

Current migration controls:

- master false + workflow false -> existing V2 evaluator/notifier path;
- master false + workflow true -> existing V2 path; workflow switch cannot bypass the kill switch;
- master true + workflow false -> existing V2 path; master switch cannot enable the workflow by itself;
- master true + workflow true -> claimed attempts route through `ConditionWatchGraph`;
- the same evaluator, notifier, repository, Tool allowlist, attempt budget, and failure policy are used in both paths;
- no LangGraph checkpointer is added in Phase 2;
- Condition Watch condition text, notification text, provider credentials, Tool results, and evaluation summary are not stored in graph coordination state or Runtime Trace events.

Parity work:

1. verify triggered transition occurs only after notifier success;
2. verify unmet watches retain the existing attempt/expiry policy;
3. verify evaluator failures persist through `mark_failure`;
4. verify notifier failures persist through `mark_failure`;
5. verify trace events expose node/outcome metadata without evaluation-summary content;
6. verify the master/workflow feature-flag matrix cannot accidentally enable graph routing;
7. keep the legacy path available behind the feature flags for rollback.

Phase 2 exit gate:

```text
Condition Watch Graph tests green
+ legacy Condition Watch tests green
+ master/workflow rollout matrix green
+ Python 3.12 / 3.13 CI green
+ Web / Discord Connector / Docker regression green
+ graph disabled by default
+ no change to polling clock or business-record authority
```

Do not enable the production graph path merely because this implementation exists. Merge the Phase 2 implementation with both switches disabled, verify deployment health, then run a controlled production pilot by enabling only the master and Condition Watch switches.

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

Phase 3 production pilot enables `CHARACTER_RELAY_LANGGRAPH_CHARACTER_TURN_ENABLED=true` only after its own parity gate passes; the Social Turn switch remains false.

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

Phase 4 production pilot enables `CHARACTER_RELAY_LANGGRAPH_SOCIAL_TURN_ENABLED=true` only after this exit gate passes.

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
