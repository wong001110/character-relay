# Character Relay OpenWiki Instructions

This file is the persistent, human-authored brief for OpenWiki. Keep it concise and stable. Normal wiki refreshes should use it to decide what to document; do not replace accepted source contracts with generated prose.

## Purpose

Generate a repository wiki that helps AI coding agents orient quickly and trace every important claim back to current source code, tests, or canonical documents. The wiki is specifically intended to reduce context drift and hallucination during parallel AI-assisted development.

## Required qualities

- Prefer **current `main` behavior** unless a page is explicitly documenting a named branch/phase.
- Clearly distinguish **implemented**, **planned**, **experimental**, **deprecated**, and **open/stacked PR** concepts.
- Never present a proposal/roadmap item as implemented without source evidence.
- Link/name exact repository paths for important claims.
- When sources conflict, show the conflict and the relevant source paths; do not invent a reconciliation.
- Treat generated UI reference art as visual/composition guidance only; never infer API fields, metrics, limits, or backend behavior from an image.
- Do not include secrets, credential values, tokens, private provider payloads, or sensitive environment values.
- Do not make an open PR look like merged repository truth.

## Priority documentation map

Maintain concise source-linked pages for:

1. Repository/service architecture and runtime boundaries.
2. Character lifecycle: Character Card -> Prompt -> Runtime -> Credential -> Test/Deployment.
3. Discord Server Workspace, connection/profile/deployment identity, channel scope, tools, and logs.
4. Conversation Intelligence: admission/planning, Topic, Episode, interruption/sequential multi-participant behavior, and authority boundaries.
5. Media pipeline: descriptor/planning knowledge vs actual Character perception, required/optional media resolution, cache/provenance.
6. Memory/RAG/Knowledge/Wiki/Graph: what is authoritative, derived, rebuildable, scoped, and current.
7. Tool model: internal context tools, external capability tools, and runtime-required operations.
8. Observability: Runtime traces, Provider traces, judge/evidence/report paths.
9. Scheduler/reminders and time semantics.
10. Web UI architecture: tokens -> UI primitives -> scrapbook components -> Character Relay shared components -> feature pages.
11. UI renovation status and approved references from `docs/ui-page-migration-plan.md` and `docs/ui-references/`.
12. Testing/CI/deployment/manual validation and the exact commands/files involved.
13. Current roadmap/status/decision documents and how they relate to implementation.

## Source authority

For implemented behavior, prioritize code, types/schemas, migrations, and tests. For intended architecture, prioritize accepted decision/contract/status documents. OpenWiki pages are synthesis/navigation and must point back to those sources.

## UI reference rule

When documenting approved UI pages, say explicitly:

- the reference image governs composition, hierarchy, and visual intensity;
- current code/API/tests govern data and behavior;
- literal generated sample copy/numbers are not implementation requirements.

## Parallel development rule

The wiki should represent the merged baseline. Active branch intent belongs in that branch's PR/evidence map until merged. If branch-specific wiki output is generated, label it clearly as branch-local and do not merge it as baseline documentation by accident.
