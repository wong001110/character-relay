# LangGraph Phase 3 — Character Turn Graph

Status: ✅ implementation complete / ⏸ production pilot deferred

## Goal

Make one Character turn a reusable LangGraph subgraph while preserving Character Relay Runtime authority.

## Implemented flow

```text
Resolve Deployment / Card / Target
→ Context + scoped RAG preparation
→ CharacterModelNode
   ├─ final output ──────────────────────┐
   └─ Tool proposal                     │
          ↓                             │
     ToolExecutionNode                  │
          ↓                             │
     CharacterModelNode (bounded loop)  │
                                        ↓
→ Smart Output parse / deterministic recovery / bounded formatting repair
→ Runtime Authority
→ Discord platform command view
```

The legacy sequential `DiscordConnectorRuntime.respond()` path and `CharacterTurnGraphRunner`
reuse the same Runtime-owned stages. The graph does not duplicate provider, retrieval, Tool,
Smart Output, credential, or repository implementations.

## Explicit Model / Tool continuation

`PromptModelTarget` now exposes one transient Tool session used by both orchestration paths:

```text
start_tool_turn()
→ advance_tool_model()
→ execute_pending_tools()
→ advance_tool_model()
```

`send_with_tools()` itself loops over those same methods, so legacy and LangGraph do not have
separate Tool Calling implementations. Tool-capable model steps are typed through the existing
`ToolCapableChatProvider` protocol rather than widening the base `ChatProvider` contract.

Preserved invariants:

- `max_tool_rounds=2` remains unchanged;
- at most one completed side-effect Tool per Character turn;
- deployment Tool allowlist remains authoritative;
- destination/platform/network safety checks remain in ToolRuntime;
- after the round budget, the next provider request has no Tools;
- Smart Output formatting repair never re-enables Tools;
- Tool results stay turn-local unless another explicit subsystem persists them.

## Graph state boundary

Graph state is coordination-only. Raw messages, prompts, private RAG excerpts, credentials,
provider responses, raw Tool arguments/results, and final reply text remain transient in
run context and are not checkpointed.

Privacy-safe state includes only classifications and references such as:

```text
resolve_status
context_status
rag_status
model_status
tool_status
tool_rounds
tool_result_count
smart_output_status
authority_status
```

## Parity / shadow coverage

Automated coverage verifies:

- direct legacy Character turn vs graph result parity for deterministic fixtures;
- early silent routing does not reach Context or Model nodes;
- explicit `Model → ToolExecution → Model` graph traversal;
- prompt-model step/session behavior matches legacy bounded `send_with_tools()` behavior;
- Runtime trace exposes node/outcome classifications without raw prompt/message content;
- rollout wiring leaves `off` and `condition_watch` on the legacy Character path;
- `character_turn` and later modes instantiate and dispatch through the graph runner.

No live request is executed twice in production for shadowing because that could duplicate
Tool side effects. Shadow comparison is therefore performed with controlled direct-runtime
fixtures until operation-level idempotency arrives in Phase 5.

The branch is synchronized with the current `main`, including the deterministic terminal
Smart Output recovery used for provider wrapper-format errors discovered during live web-search
testing. The final Phase 3 CI therefore validates the Character graph against that same parser.
No temporary migration or cleanup workflow remains in the Phase 3 net diff.

## Rollout

Production remains on:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=condition_watch
```

The Phase 3 code path is present but inactive. When the combined Phase 3 + Phase 4 live
verification begins, `character_turn` can be used as an intermediate isolation mode:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=character_turn
```

Rollback from Character Turn remains:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=condition_watch
```

## Implementation exit gate

- legacy Character Turn regressions green;
- graph direct-runtime parity green;
- explicit model/Tool continuation preserves Tool Calling V2 bounds;
- Smart Output formatting repair cannot repeat Tool side effects;
- privacy-safe Runtime trace contains orchestration classifications only;
- cumulative rollout wiring covered by tests;
- Python 3.12/3.13 Ruff, strict mypy and pytest green;
- Web, Discord Connector and Docker regressions green;
- Railway smoke green.

The production pilot portion of the original Phase 3 gate is intentionally deferred so it can
be tested together with Phase 4 in one controlled rollout session.
