# Observability & Runtime Control Status

Status: **ROADMAP CREATED / IMPLEMENTATION STARTING**

Branch: `agent/observability-runtime-control`

This document tracks the post-V4 optimization PR.

## Scope

- Conversation Intelligence Inspector for Learned State and Topic changes.
- AI Utility Gateway Free Pool quota/reset/health observation and automatic cooldown recovery.
- Portal-controlled Conversation Burst / Turn Collector timing with dynamic Connector sync and no restart requirement.

## Initial defaults

- Quiet window: 3,000 ms.
- Maximum wait: 10,000 ms.
- Max messages: 5.
- Max characters: 1,500.

## Current implementation state

- Roadmap and invariants documented.
- Runtime/UI implementation pending in this branch.
- Draft PR remains the single integration point for all work in this roadmap.
