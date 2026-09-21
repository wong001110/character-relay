# Project state

Reviewed: **2026-09-21**. This is the single current project status and takeover record.

## Current task and authorization

| Item | State |
| --- | --- |
| Repository | `wong001110/character-relay` |
| Verified merged runtime baseline | `3cd183d460812d16cfb0c6d8dbae305d8ef61363` (PR #205, merged 2026-09-13) |
| Planning branch | `docs/ai-native-group-chat-handoff` |
| This change | Documentation, navigation, accepted decisions and Work handoff only |
| Accepted product direction | [Discord group-chat core plan](docs/plans/discord-group-chat-core.md) |
| New feature implementation | **NOT_STARTED — excluded from this PR** |
| Source-tree relocation | **NOT_STARTED — target boundaries documented, no files moved** |
| Merge / deployment | Not requested by this task |
| Next executor | Work, after the user explicitly starts implementation there |

This branch intentionally changes no application source, test behavior, schema, dependency,
workflow execution or deployed service. Do not describe the target architecture as already live.
Recheck branch/HEAD and reconcile concurrent work before beginning implementation.
PR #203 (local execution/embodiment roadmap) is separate, unmerged work and is not incorporated here.

## What is already implemented at the baseline

PR #205 made proactive nomination compatible with `ignore`, tightened some address heuristics,
removed broad automatic Belief/Episode/Fabric injection from ordinary context, and stopped
relationship scores directly promoting participation. Scoped internal recall tools and the
existing account, credential, tool, job, media and delivery foundations remain.

That merge did **not** complete the newly accepted simplification. In particular:

| Existing limitation / remaining work | Inspect before implementation |
| --- | --- |
| Historical message schemas lack per-message Reply relationships; webhook response-to-source links need strengthening | `src/echo_masque/api/connector_schemas.py`, `connectors/discord/src/types.ts`, `index.ts`, `webhookManager.ts` |
| Selected conversation vs trigger attribution and fallback/persistence handling can diverge | `character_turn_context_v3.py`, `connector_runtime.py`, `api/routes/smart_participation_vnext.py` under `src/echo_masque/` |
| Same-role re-entry is still limited by completed-role/unique-turn guards | `src/echo_masque/orchestration/social_turn_graph.py`, `connectors/discord/src/smartOutput.ts` |
| Ordinary context still invokes self-claim correction/extraction and entity-gap handling | `src/echo_masque/character_turn_context_v3.py`, `current_turn_belief_v3.py` |
| Coarse relationship text still derives from multidimensional stored social state | `src/echo_masque/social_intelligence_v3.py`, `social_event_runtime.py` |
| Recall needs explicit current-room/subject/source eligibility, not only broad server or any-source perception checks | `src/echo_masque/internal_context.py`, `persistence/belief_repository.py` |
| Provider trace summary mode can retain prose; operation diagnostics are distributed | `src/echo_masque/providers/trace.py`, `runtime_trace_buffer.py`, trace/debug routes |
| Roast-specific UI, prompts, session routes and scheduling still exist | interaction modules/routes, `connectors/discord/src/index.ts`, Portal interaction UI |

These are source-review findings and implementation entry points, not claims of reproduced
production incidents. Some paths use directory-relative shorthand above; architecture.md provides
full ownership roots. Reproduce changed behavior in P1 before assigning severity or claiming fixes.

## Accepted, not implemented

The active plan owns the complete decisions, acceptance cases and integration dispositions:
bounded multi-bot participation with valid silence; group-aware provenance and authority;
private drafts with send-time freshness checks; short relationship notes; explicit memory writes
and optional scoped recall; Roast retirement; safer Discord delivery; metadata-first observability;
and removal of redundant hot-path work without weakening safety or evaluation capability.

Initial multi-role limits (3 distinct roles / 6 visible speaking turns / 2 per role) are configurable
validation starting points, not measured optima. They are ceilings, not participation quotas.

## Implementation checkpoints

The main agent may revise phase boundaries with evidence; it must retain all plan requirement IDs.
Only update these states after real work. Never pre-mark a phase complete because its design exists.

| Checkpoint | Outcome | Status |
| --- | --- | --- |
| P0 | Accepted plan, single-policy/state entry and source ownership map | **DOCUMENTATION_PREPARED** |
| P1 | Reproduce baseline group-chat failures; define scoped provenance/security and measurement fixtures | NOT_STARTED |
| P2 | Discord event/Reply/source handling, reliable delivery and non-blocking ingress | NOT_STARTED |
| P3 | Bounded multi-role participation and draft freshness/continuation | NOT_STARTED |
| P4 | Explicit notes, lightweight relationships, removal of automatic simulation and Roast | NOT_STARTED |
| P5 | Interaction observability, Portal simplification and justified adapter reuse | NOT_STARTED |
| P6 | Integrated evidence, physical source cleanup, removal audit and release handoff | NOT_STARTED |

## Work takeover

1. Read AGENTS.md, this state and the active plan. Check the actual Git branch and whether the
   documentation PR is merged; do not start from old main without these decisions.
2. After the user's execution instruction in Work, start from this planning branch or its merged
   descendant and create an implementation branch. Do not import another open PR automatically.
3. Begin with P1: trace actual ingress-to-delivery call sites and characterize the accepted
   negative/positive group-chat cases. Record available Python/Node/PostgreSQL/browser facilities.
4. Use the proposed feature boundaries in architecture.md; choose the minimal safe physical moves
   per phase, preserving imports, API contracts and test discovery until their consumers migrate.
5. Update this table and evidence after each coherent phase; leave the next action concrete.
   No extra per-agent ledger or parallel handoff file is required.

## Evidence and limits for this documentation task

Baseline branch, repository tree, PR list, current development entry points, service architecture
and security contract were read through the connected GitHub interface. Local Git clone was
unavailable (DNS resolution failure), so this is not a claim of a full local checkout or test run.
Documentation checks and exact changed-path/source-tree comparisons are recorded in this PR.
No new runtime pytest, model-quality, production Discord or security acceptance is claimed.
Inherited CI results, where consulted, remain tied to their original commits.

Before implementation/release, resolve: effective Message Content availability; real role/tool
permissions and private-thread policy; scoped historical-data migration; safe cancellation and
uncertain delivery; availability of live-model credentials and isolated external test targets.
These are verification tasks, not assumed passes or authorization to access private production data.
