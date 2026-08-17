# Conversation Intelligence Research Notes

Status: supporting notes for the Conversation Intelligence Architecture proposal

This file records the external architecture patterns discussed while designing Character Relay. These systems are references, not implementation requirements.

## 1. ChatGPT product memory behavior

Public OpenAI product documentation describes two user-facing memory concepts:

- **Saved Memories**: durable information ChatGPT may keep for future conversations.
- **Reference Chat History**: information from past chats can be used without every past message becoming a permanent Saved Memory.

The useful architecture lesson for Character Relay is not to treat the entire transcript as durable Memory.

A comparable separation is:

```text
Conversation / Episode history
        -> searchable evidence

Durable Character Memory
        -> selected facts/preferences/relationships worth retaining
```

Important caveat: OpenAI does not publicly document the full internal ChatGPT memory retrieval stack, vector store, Topic Graph, ranking formula, or exact consolidation pipeline. Character Relay should use the public product behavior only as conceptual evidence, not claim to reproduce ChatGPT internals.

Reference discussed:

- OpenAI Help Center: Memory / Saved Memories / Reference Chat History

## 2. LangGraph / LangChain memory

The LangGraph/LangChain memory model separates:

```text
short-term / thread state
long-term memory
```

Long-term memory discussions also distinguish different cognitive roles such as semantic, episodic, and procedural memory, and allow memory updates either on the request hot path or through background processing.

Character Relay takeaway:

- recent conversational state should not equal durable memory,
- not every Discord message needs an immediate Memory Judge call,
- durable consolidation can happen after the visible response when correctness does not depend on it.

Reference discussed:

- LangChain/LangGraph Memory documentation

## 3. Generative Agents

The Generative Agents architecture uses a memory stream and retrieves memories with signals including:

```text
relevance
recency
importance
```

It also creates higher-level reflections from accumulated experiences.

Character Relay takeaway:

```text
raw Episodes
   -> selected durable Memories
   -> repeated/related Memories
   -> higher-level reflection / Wiki understanding
```

This is more suitable for social roleplay than turning every message into one permanent fact.

Reference discussed:

- Park et al., "Generative Agents: Interactive Simulacra of Human Behavior"

## 4. Letta

Letta exposes a hierarchy where some memory is kept in core context while larger archival memory can be searched when needed. Agent-controlled memory/retrieval tools are possible, but they operate inside explicit memory boundaries.

Character Relay takeaway:

- Character-driven Internal search is useful,
- it should be an **escape hatch**, not the only retrieval mechanism,
- the agent should not receive unrestricted database authority,
- Runtime injects scope/security while the Character supplies semantic intent.

Comparable Character Relay split:

```text
Runtime-prefetched context
+ bounded Internal tools such as memory.search
```

Reference discussed:

- Letta memory/context hierarchy documentation

## 5. Zep / Graphiti

Graphiti models incoming conversations/documents as Episodes and extracts entities and relationships while preserving provenance. It also represents temporal changes to facts/relationships rather than assuming the latest statement simply erases history.

Character Relay takeaway:

```text
Episode = source/provenance
Entity/Relationship = structural interpretation
Memory = durable cognition derived from evidence
```

This is useful for long-running group conversations where facts, opinions, relationships, and preferences can change over time.

A future temporal Memory/Graph layer should be able to represent:

```text
fact valid at time A
fact revised/invalidated at time B
source Episodes retained
```

References discussed:

- Zep / Graphiti overview
- Graphiti Episodes documentation

## 6. Microsoft GraphRAG

GraphRAG builds structured entities/relationships from source text and produces community-level summaries. Local and global retrieval can operate at different levels of the graph/summary hierarchy.

Character Relay takeaway:

A future Wiki/Graph system can support different levels of questions:

```text
local question
-> entity / relationship / source Episodes

broad question
-> Topic/community-level consolidated summary
```

This is a later-stage direction. It should not replace provenance or raw evidence.

Reference discussed:

- Microsoft GraphRAG documentation / global search architecture

## 7. RAPTOR

RAPTOR recursively clusters and summarizes text into a hierarchy from detailed source chunks to broader summaries.

Character Relay takeaway:

Wiki/consolidation does not need to remain a single flat overview page. A future hierarchy could be:

```text
Episodes / sources
   -> local Topic summaries
   -> Entity/Topic pages
   -> broader community/category summaries
```

This should only be considered after Topic identity, provenance, and Memory boundaries are reliable.

Reference discussed:

- RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval

## 8. CoALA

CoALA frames language agents as systems containing structured memory and action components rather than treating the LLM prompt as the entire architecture.

Character Relay takeaway:

The Character model should operate inside a bounded action/context system:

```text
LLM semantic decision
-> structured action proposal
-> Runtime authority/validation
-> execution
```

Internal cognitive actions and external world actions should be distinguishable.

Reference discussed:

- CoALA: Cognitive Architectures for Language Agents

## 9. Combined design pattern for Character Relay

Across these references, several common patterns are useful:

### Separate raw evidence from consolidated knowledge

```text
raw source / Episode
!= durable Memory
!= Wiki summary
```

### Retrieval is selective

Do not put all history in the prompt. Retrieve a bounded candidate set based on current context.

### Higher-level understanding is derived

Reflection/Wiki/community summaries should retain source provenance and be refreshable/staleable.

### Agent autonomy is bounded

An LLM can decide semantic intent or request additional context, but Runtime should own:

- scope,
- identity,
- candidate validity,
- permissions,
- lifecycle,
- side-effect authorization,
- persistence.

### Temporal validity matters

Long-running roleplay and social systems need to handle changed preferences, relationships, beliefs, and facts without deleting their historical provenance.

---

## 10. Character Relay interpretation

The research supports the architecture proposed in the companion design document:

```text
Episode
Topic
Memory
Wiki
Media Object
Entity / Graph
```

with the following primary runtime flow:

```text
candidate retrieval
-> Utility Intelligence structured plan
-> Runtime validation/retrieval
-> Character Turn Contract
-> Roleplay LLM
-> post-turn consolidation
```

This is deliberately a hybrid design rather than a direct clone of ChatGPT, Letta, Graphiti, GraphRAG, or any other system.