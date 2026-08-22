# Character Relay documentation index

Status: **canonical navigation index**

This directory contains current contracts, operational guides, accepted plans, and historical delivery records. A filename containing “roadmap”, “phase”, or “status” is not proof that the described work is current or merged. Verify the document header, current source, tests, and Git branch before using it.

## Authority order

For implemented behavior:

1. source, schemas/types, migrations, and tests on the current branch;
2. current `main` when establishing the merged baseline;
3. the task-relevant canonical contracts below;
4. generated OpenWiki pages;
5. proposals, branch status records, PR text, and chat history.

For intended product or UI direction, accepted contract/decision documents lead, but they do not prove implementation. When two sources conflict, report the conflict instead of combining them into a plausible answer.

## Start here

| Need | Read first |
| --- | --- |
| Any AI coding task | `AGENTS.md`, `docs/ai-agent-development-workflow.md`, `docs/agent-handoff.md` |
| Repository/service ownership | `docs/architecture.md` |
| Intelligence/runtime authority | `docs/intelligence-core-v3-architecture.md` |
| Authentication/security | `docs/phase-15-security.md`, `docs/security.md` |
| Railway/storage | `docs/railway-deployment.md`, `docs/storage-safety.md` |
| Discord workspace/runtime | `docs/discord-server-workspace.md`, `connectors/discord/README.md` |
| UI implementation | `docs/ui-ux-contract.md`, `docs/ui-component-library.md`, `docs/ui-page-migration-plan.md`, approved reference image |
| Manual release checks | `docs/manual-validation.md` |

## Current canonical contracts

- `architecture.md` — current service boundaries and module ownership.
- `intelligence-core-v3-architecture.md` — merged Intelligence Core authority model and forbidden Topic reintroductions.
- `ai-agent-development-workflow.md` — evidence and branch protocol for coding agents.
- `security.md`, `phase-15-security.md` — security boundary and production authentication configuration.
- `railway-deployment.md`, `storage-safety.md` — supported deployment/storage shape.
- `ui-ux-contract.md`, `ui-component-library.md`, `ui-page-migration-plan.md` — UI contract and approved migration state.
- `http-target-contract.md` — custom external target boundary.
- `server-timezone-runtime.md` — server-local time semantics.

Subsystem contracts such as `context-rag-v1.md`, `media-epistemic-observability.md`, `provider-tracing.md`, `smart-output-v1.md`, and `tool-calling-v2-implementation.md` remain useful only where current source/tests still implement the stated boundary.

## Accepted plans and delivery records

Roadmaps and phase documents explain why a subsystem exists and may contain still-valid invariants. Their branch names, pending gates, file inventories, and test counts are historical snapshots unless their header explicitly says otherwise.

- LangGraph: `langgraph-roadmap.md`, `phase-3-character-turn.md`, `phase-4-social-turn.md`, `phase-5-durable-runtime.md`.
- Evaluation: `phase-14-experiment-matrix.md`, `phase-16-*.md`.
- Discovery/presence: `character-discovery-roadmap.md`, `deployment-presence-discovery-acceptance.md`.
- Stabilization/control plane: `stabilization-vnext-*.md`, `conversation-intelligence-control-plane-*.md`.
- UI delivery reviews: `ui-phase2-character-workflow.md`, `ui-complete-migration-review.md`.

## Superseded historical context

The following are retained to explain earlier decisions, not to direct new implementation:

- `conversation-intelligence-architecture.md`
- `conversation-intelligence-decisions.md`
- `conversation-intelligence-research-notes.md`
- `conversation-intelligence-v4-roadmap.md`
- `product-roadmap-rag-and-smart-participation.md`
- `smart-participation-v3.md`

Intelligence Core v3 removed Topic authority and supersedes Topic-centric routing, memory, Wiki, Discovery, and continuation proposals in those documents.

## Documentation maintenance rules

- Put new product authority in a canonical contract, not a generated wiki page.
- Update this index when adding, replacing, or retiring a canonical document.
- Prefer updating an existing subsystem contract over adding another status file.
- Keep branch-local checklists and inventories in the PR description when they are not durable product documentation.
- Never copy secrets, tokens, private payloads, generated UI sample data, or provider credentials into documentation.
- Use `CHARACTER_RELAY_*` for application settings. `ECHO_MASQUE_LIVE_*` names in GitHub Actions are workflow secret names and are not runtime configuration.
