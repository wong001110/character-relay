# Discord Smart Output V1

Smart Output V1 turns one admitted Character Relay turn into one validated Discord social action. It sits after Routing / Smart Participation and before Discord execution.

```text
Discord event
→ Routing / Smart Participation
→ Context + Expression Retrieval
→ Character LLM
→ Smart Output proposal
→ Runtime validation
→ Discord execution
```

The model proposes behavior. Runtime remains the execution authority.

## Action contract

A character chooses exactly one action:

```text
ignore
message
react
sticker
```

The control response is one machine-readable line:

```text
[[CR_OUTPUT {...}]]
```

The control line is not sent to Discord.

### Ignore

```json
{"action":"ignore"}
```

No Discord state changes are made.

### Message

```json
{
  "action": "message",
  "reply_to": "trigger",
  "content": [
    {"text": "你 😂 真的认真的？ "},
    {"emoji": "e1"},
    {"text": " "},
    {"mention": "p1"}
  ]
}
```

`content` is ordered. Every item contains exactly one field:

- `text` — normal visible text; Unicode Emoji may appear directly here;
- `emoji` — one prompt-local alias for a retrieved custom Server Emoji;
- `mention` — one runtime-supplied participant alias.

Omitting `reply_to` means normal channel speech. Setting `reply_to` uses only one supplied message alias.

V1 permits at most one retrieved custom Emoji in one message. Unicode Emoji are not subject to this resource limit.

### Reaction

```json
{
  "action": "react",
  "target": "trigger",
  "emoji": "e1"
}
```

The Emoji alias must refer to one of the retrieved resources and that resource must allow `reaction`.

### Sticker

```json
{
  "action": "sticker",
  "sticker": "s1"
}
```

A Sticker may optionally specify `reply_to`.

## Reference isolation

The model is not given raw Discord user IDs, deployment IDs, message IDs, custom Emoji IDs, Sticker IDs, or expression resource keys as behavioral references.

Prompt-local aliases are used instead:

```text
trigger
m1, m2, ...
p1, p2, ...
e1, e2, ...
s1, s2, ...
```

`eN` aliases refer only to retrieved Emoji candidates and `sN` aliases refer only to retrieved Sticker candidates. After generation, the backend resolves every alias back to its hidden runtime reference. The Discord Connector validates the resolved reference again before executing anything.

The current character is intentionally excluded from the mentionable participant list, and Connector validation rejects a self-reference if one is injected anyway.

## Expression Retrieval reuse

Smart Output does not create a second Emoji / Sticker selection system.

The existing pipeline remains:

```text
Server expression dictionary
→ available / enabled filtering
→ allowed-action filtering
→ semantic retrieval + recent-use penalty
→ Top-K candidates
→ prompt-local eN / sN aliases
→ Smart Output
→ live Discord resource validation
```

The full Server expression dictionary and raw Discord expression IDs are never sent to the character model.

## Failure policy

Smart Output V1 is fail-closed:

1. strict schema parse;
2. reference/resource validation;
3. if a prompt-model response is invalid, regenerate once;
4. validate again;
5. if still invalid, convert the turn to `ignore`;
6. do not partially execute an invalid action.

Examples of rejection include unknown participant aliases, unknown message aliases, unknown expression aliases, wrong resource action, unavailable resources, or invalid message content.

A failed Reaction does not silently become an inline Emoji. A bad Mention does not result in a partially sent message.

## Mention execution

Human Mentions are converted to Discord mentions only after the runtime approves the participant. Discord delivery uses an explicit allowed-user list; broad mention parsing stays disabled.

Character Mentions compile to the active Character Relay address alias and may trigger another character turn. Bot-to-bot continuation keeps the existing depth/response budget and uses one shared seen-set for the whole human-triggered chain. A character is reserved when it receives a turn, so it cannot re-enter through its own branch or a sibling branch later in the same chain.

## Reply semantics

For shared Bot identity, `reply_to` is executed as a real Discord reply to the validated target message.

For webhook character identity, Discord webhook delivery does not provide the same native reply-reference path used by the shared Bot. V1 therefore preserves the character webhook identity and degrades an otherwise valid `reply_to` request to a direct webhook message. The runtime records this as `webhook_reply_to_direct` rather than pretending a native reply occurred.

## Compatibility

Production prompt-model deployments use Smart Output V1.

Deterministic `stable` / `fragile` development targets are adapted from their legacy text result into a Smart `message` action so existing test/demo fixtures continue to work.

The old Expression Decision shape remains available internally for legacy observability and compatibility while the Discord Connector migrates to `smart_output` as the primary action contract.

## Non-goals for V1

Smart Output V1 does not add:

- RAG or Vector Memory;
- LangChain;
- Tool Calling;
- Local Participation Judge;
- multiple custom Server Emoji in one generated message;
- autonomous multi-step agent loops.

Those layers can be added later without changing the Routing → Participation → Context → Smart Output → Execution boundary.
