# Conversation Intelligence V4 — Implementation Status

Updated: 2026-08-14

Branch: `agent/conversation-intelligence-v4`

PR: #166 — Draft, do not auto-merge.

## Live on the V4 branch

### Turn Collector / Conversation Burst

Ordinary unresolved Smart Participation text is collected before the heavy Discord per-channel Runtime queue.

Defaults:

- quiet window: 1.5 s
- hard max wait: 4 s
- max 5 messages
- max 1,500 collected characters

Explicit Bot mentions, replies, explicit Character/group addressing, rich Discord content, URL-bearing messages, interaction-controlled turns, and recovery turns currently bypass collection or force-flush an older burst.

Earlier burst messages retain their own source message/author/timestamp identity in recent context. `/api/smart-participation/resolve` receives ordered burst provenance, while Character Runtime still receives the latest real source message as the current turn.

### Burst observability

The Connector records bounded telemetry without copying raw message text:

- burst ID
- flush reason
- message count
- author count
- total characters
- opened/flushed timestamps
- collection latency
- collapsed message count
- source message IDs

Connector health also exposes cumulative candidate/bypass/burst/collected/collapsed counters and the latest burst metadata.

### Pre-E5 runtime gates

Smart Participation now reuses the existing TypeScript Runtime state before E5.

E5 is skipped when the Runtime can already determine:

- low-information handling
- channel cooldown
- channel rate limit
- all Smart candidates blocked by profile/avoid/per-character cooldown state

When only some candidates are blocked, only the remaining deployment IDs are sent to semantic scoring.

The preflight does not queue a speaker selection. `resolveAudience()` still executes the authoritative final Smart Participation decision afterwards using the same state.

### Server-wide scope correction

Pending Smart selections now retain the actual runtime channel/thread scope supplied by routing. `consumeSmartSelection()` uses that stored scope rather than deriving cooldown/admission scope again from a server-wide deployment template.

This keeps channel cooldown/rate-limit state consistent between pre-E5 gating and final selection for `all_except` deployments.

### Conversation-aware resolver

Normal unresolved Smart Participation prefers:

`POST /api/smart-participation/resolve`

Legacy `/semantic-score` remains only as a rolling-deploy fallback when `/resolve` is absent (`404/405`).

The resolver currently supplies evidence, not final admission authority. Raw E5 remains separate and Graph/Learned State do not yet boost eligibility.

### Participation Semantic Profile V2

Positive participation context is embedded with Character identity:

- participation style
- group role
- topics
- keywords
- trigger cues

Hard rules such as avoid phrases, cooldowns, permissions, and enablement remain deterministic.

### Unified Turn Intelligence foundation

`turn-intelligence-v1` supports bounded optional gray-zone decisions for Topic continuity, Speaker choice, Knowledge route, and one already-authorized pending Tool continuation.

Participation tie-break already uses the Speaker contract with the existing demote-only/no-boost invariant. Full Topic/RAG/Tool consolidation is still pending.

### Conversation Intelligence Graph foundation

SQLite Graph storage and Shadow observation are present. Current Shadow observation records only directly provable public evidence such as:

`Actor -> PARTICIPATED_IN -> ConversationBurst`

Graph evidence does not yet change speaker admission.

## Current validation checkpoint

The live Turn Collector ingress checkpoint passed:

- Discord Connector typecheck
- all 108 Connector tests at that checkpoint
- Connector build/image
- Python 3.12 Ruff/Mypy/Pytest
- Python 3.13 Ruff/Mypy/Pytest
- Web typecheck/tests/build
- production Docker smoke
- Railway Smoke #1165

Burst observability and Runtime pre-E5 gating were each committed only after their guarded Connector typecheck/tests/build passed. This status commit triggers the full repository validation suite for the combined checkpoint.

## Still pending

1. Media-aware burst provenance without changing Character epistemic truth.
2. Shared/server-authoritative deterministic participation scoring to eliminate Portal/Connector drift.
3. Utility only after deterministic + E5 + contextual evidence reaches a real final gray zone.
4. Live Topic/RAG/pending-Tool consolidation through Turn Intelligence.
5. Retirement of the old `SemanticRoutingJudgeService` cascade after parity coverage.
6. Graph Shadow expansion from authoritative Topic/Event/Media/Character sources.
7. Learned State: Dynamic Interest, Expertise, Stance, Relationships, Conversation Ownership, Salience, Participation Fatigue, contradiction handling and decay.
8. Graph/Learned-State reranking only after measured Shadow quality is acceptable.
9. Durable multi-replica social state where process-local bookkeeping is insufficient.
10. Final selection-quality, latency, Utility-call-count, Railway RAM/storage and regression validation.
