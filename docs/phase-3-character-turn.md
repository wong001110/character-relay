# LangGraph Phase 3 — Character Turn Graph

Status: 🚧 in progress

## Goal

Make one Character turn a reusable LangGraph subgraph while preserving Character Relay Runtime authority.

## Slice A — direct-runtime parity

Current implementation:

```text
Resolve Deployment / Card / Target
→ Context + scoped RAG preparation
→ Character model + existing bounded ToolRuntime loop
→ Smart Output parse / bounded formatting repair
→ Runtime Authority
→ Discord platform command view
```

The legacy sequential `DiscordConnectorRuntime.respond()` path and `CharacterTurnGraphRunner` call the same Runtime-owned stage methods. The graph does not duplicate provider, retrieval, Tool, Smart Output, credential, or repository implementations.

Graph state is coordination-only. Raw messages, prompts, private RAG excerpts, credentials, provider responses, raw Tool arguments/results, and final reply text remain transient in run context and are not checkpointed.

Production Discord routing is unchanged in Slice A. `CHARACTER_RELAY_LANGGRAPH_MODE=condition_watch` remains the live pilot setting.

## Slice B — explicit model / Tool continuation

After Slice A parity is green, split the existing bounded `PromptModelTarget.send_with_tools()` continuation into explicit Character Turn graph transitions while keeping the same ToolRuntime authority:

```text
CharacterModelNode
├─ final output → SmartOutputNode
└─ Tool proposal → ToolExecutionNode
                    ↓
                CharacterModelNode
```

Required invariants:

- `max_tool_rounds=2` remains unchanged;
- at most one completed side-effect Tool per Character turn;
- deployment Tool allowlist remains authoritative;
- destination/platform/network safety checks remain in ToolRuntime;
- a formatting repair never re-enables Tools;
- Tool results stay turn-local unless another explicit subsystem persists them.

## Slice C — shadow comparison

Run legacy and graph orchestration against controlled direct-runtime fixtures and compare:

- action: silent / reply / expression;
- Smart Output authority result;
- Tool trace classifications and counts;
- Context/RAG status;
- failure behavior;
- no duplicate side effects.

No public Discord cutover occurs during shadow comparison.

## Slice D — selected Discord pilot

Only after direct/shadow parity passes, wire `CHARACTER_RELAY_LANGGRAPH_MODE=character_turn` to selected internal Character traffic. `condition_watch` remains included because rollout modes are cumulative.

Rollback remains one value:

```text
CHARACTER_RELAY_LANGGRAPH_MODE=condition_watch
```

## Exit gate

Phase 3 is complete only when:

- legacy Character Turn regressions remain green;
- graph direct-runtime parity is green;
- explicit model/Tool continuation preserves Tool Calling V2 bounds;
- Smart Output formatting repair cannot repeat Tool side effects;
- privacy-safe trace contains orchestration classifications only;
- selected Discord pilot matches legacy behavior;
- Python 3.12/3.13 Ruff, strict mypy and pytest are green;
- Web, Discord Connector and Docker regressions are green;
- production rollback to `condition_watch` is verified.
