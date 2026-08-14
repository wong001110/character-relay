# Conversation Intelligence V4 — Implementation Validation

Status: **IMPLEMENTATION COMPLETE / FULL RELEASE VALIDATION RUNNING**

Branch: `agent/conversation-intelligence-v4`

Draft PR: #166 — Smart Participation V4: Conversation Intelligence Graph

This document records the implemented V4 scope before the final full CI/Railway release gate. The PR remains Draft and must not be merged without explicit owner approval.

## Implemented phases

- **Phase 0 — Measurement and compatibility:** V3/V4-compatible tracing, Turn Intelligence telemetry, speaker-plan/shadow parity, raw E5/context/Utility separation, and independently disableable rollout modes.
- **Phase 1 — Adaptive Turn Collector:** bounded channel/thread Conversation Bursts with quiet/max windows, explicit-address bypass, original source IDs, and image-only visible attachment collection.
- **Phase 2 — Pipeline reorder:** explicit audience and cheap deterministic eligibility gates precede E5; Utility is no longer a raw-E5 tie breaker and runs only on final ambiguity.
- **Phase 3 — Conversation-aware resolver:** `/api/smart-participation/resolve` accepts bounded burst/scope/candidate evidence and can return an authoritative server speaker plan in active mode while preserving off/shadow compatibility.
- **Phase 4 — Conversation Intelligence Graph:** SQLite graph nodes/edges, bounded provenance/lifecycle metadata, public/private scope separation, Topic/Burst/Actor/Character observations, and shadow-compatible derived evidence.
- **Phase 5 — Graph-assisted reranking:** named Graph and Learned State evidence may rerank/demote already-eligible candidates but cannot lift a below-threshold or deterministically blocked Character into eligibility. Final Utility sees only the bounded final candidate set.
- **Phase 6 — Character Learned State:** interest, expertise, stance, relationship, conversation ownership, salience, and participation fatigue with confidence, positive/negative evidence, bounded provenance, contradiction handling, and type-specific decay. Expertise/Stance updates require structured authenticated evidence rather than self-asserted Character prose.
- **Phase 7 — Topic/Media relationships:** Topic Memory remains lifecycle authority; authoritative Character media references project PERCEIVED relationships into the Graph; active Topic→Media evidence can narrow historical recall; SHA understanding remains reusable while Character epistemic state remains scoped.
- **Phase 8 — Durable social state:** server-side channel cooldown/window accounting, per-Character cooldown, recent-speaker anchor, outcome observation, restart/multi-replica-safe recovery, and short-lived conversation ownership.

## Final edge cases completed

### Durable low-information restart recovery

The Connector keeps the existing local hot path. Only when a recognized low-information Smart Participation turn cannot resolve a recent speaker locally after process-state loss does it query the server's durable recent-speaker anchor. A returned deployment is revalidated through the same local lightweight candidate/admission machinery, preserving profile enablement, avoid rules, thresholds, and one-lightweight-follow-up behavior. Backend failure is fail-open to the existing local path.

### Visible-image Conversation Burst provenance

Pure directly visible image attachments can participate in a Conversation Burst with immediately following text. Mixed/non-image attachments, embeds, URLs, video/link inspection, stickers, and other rich-content paths retain their previous bypass/Tool policy.

The Connector transmits only bounded original image source message IDs. Media Runtime resolves each image using its original Discord message ID and records per-Character perception against that source message. Objective SHA-based understanding is still reusable, while Conversation Media/Graph provenance is not reassigned to the burst's final text message.

## Validation already passed before the full release gate

- Python Ruff for V4-touched runtime paths.
- strict Mypy across the Python source tree.
- targeted RAG / Character Context / Tool continuation / Learned State / V4 resolver regression tests.
- targeted Media Runtime provenance, attachment schema, and V4 resolver tests.
- Discord Connector TypeScript typecheck.
- Discord Connector Vitest suite: **126 / 126 tests passed** in the final edge-case guarded run.
- Discord Connector production build.
- `git diff --check` for the final edge-case commit.
- standalone API/Learned-State import smoke after removing the eager API package import cycle.

## Release gate still required

The implementation is not declared release-validated until the normal repository workflows run against a non-bot branch commit and report:

1. full CI green, including Python, Web, Discord Connector, Docker and repository-wide tests/checks;
2. Railway Smoke green;
3. Public Demo Status Check green or otherwise confirmed unrelated/non-blocking according to repository policy;
4. no new explicit-address, Smart Output, media-epistemic, or durable-state regression;
5. PR #166 remains Draft/unmerged until explicit owner approval.

If a release-gate regression is found, fix it in this same branch and PR; do not split the implementation into another PR.
