# Character Relay documentation

Status: **canonical navigation index**

Choose the path that matches what you are trying to do:

| I am… | Start here |
| --- | --- |
| Using Character Relay | [User guide](user/README.md) |
| Running production or handling an incident | [Operator guide](operator/README.md) |
| Developing the product | [Developer guide](developer/README.md) |
| Designing or reviewing an evaluation | [Evaluation path](#evaluation-and-calibration) |
| An AI coding agent taking over work | repository `AGENTS.md`, then [agent map](agent-map.md), [AI agent workflow](ai-agent-development-workflow.md), and [agent handoff](agent-handoff.md) |
| Looking for current authority | [Canonical contracts](contracts/README.md) |
| Planning future local device execution | [Local execution and embodiment roadmap](local-execution-roadmap.md) — planned/deferred, not implementation proof |
| Investigating why an old design exists | [Historical/reference index](history/README.md) |

## Product support snapshot

Discord is the current production connector. New Connection and Deployment creation is Discord-only; legacy WhatsApp and Telegram records remain readable/deletable for compatibility, but are not supported runtimes.

Intelligence Core v3 is the current intelligence authority. Topic fallback, Topic-scoped durable memory, `topic_id` continuation authority, and Topic-driven Wiki/Discovery behavior must not be reintroduced. See the [v3 contract](intelligence-core-v3-architecture.md).

## Fast links

- [Set up Discord](user/discord-setup.md)
- [Debug Discord](user/discord-debugging.md)
- [Deploy on Railway](railway-deployment.md)
- [Security and privacy](security.md)
- [Run release checks](manual-validation.md)
- [Mutation testing](mutation-testing.md)
- [Portal development and mock UI review](portal-development.md)
- [Intelligence repair scope](intelligence-repair-scope.md)
- [Repository architecture](architecture.md)
- [Planned local execution and embodiment](local-execution-roadmap.md) — future Character Relay Local / device / live-view direction; not implemented
- [Turn Director and focused Roleplay implementation record](turn-director-prompt-implementation.md) — verify branch/commit status before treating it as merged behavior
- [Current branch execution ledger](active-development-plan.md) — use only when its recorded branch matches the checkout

## Evidence and authority

For implemented behavior, use this order:

1. source, schemas/types, migrations, and tests on the current branch;
2. current `main` when establishing the merged baseline;
3. task-relevant canonical contracts;
4. maintained agent navigation and handoff;
5. proposals, branch records, PR text, and chat history.

Accepted product/UI contracts may lead intended direction, but they do not prove implementation. When sources conflict, report the conflict instead of inventing a compatible answer. A filename containing “roadmap”, “phase”, or “status” is not proof that the work is current or merged.

## Agent navigation

[Agent map](agent-map.md) and [agent handoff](agent-handoff.md) are the maintained entry points
for a new coding agent. They link to source, tests, and contracts but never outrank them. Update
only the affected map row when a coherent phase changes module ownership, validation ownership, or
a canonical boundary; keep branch-only work in its active plan until merged.

## Evaluation and calibration

Follow this order when authoring or reviewing evaluation work:

1. [Experiment Matrix](phase-14-experiment-matrix.md) for persisted runs, comparison, and exports.
2. [Evaluation authoring](phase-16-authoring.md) for approval boundaries and immutable datasets.
3. [AI-assisted authoring](phase-16-ai-authoring.md) for draft-only AI assistance.
4. [Calibration](phase-16-calibration.md) and [rubric coverage](phase-16-rubric-coverage.md) for quality review.
5. [Release / live acceptance](phase-16-release.md) for retained live checks.

These documents describe evaluation workflow and evidence boundaries; they are not a claim that
local synthetic fixtures prove production model quality.

## Maintenance rules

- Put durable product authority in a canonical contract, not an agent-navigation page or branch ledger.
- Prefer updating an existing contract over adding another status document.
- Keep old filenames when links depend on them; classify them in the historical index instead of silently presenting them as current.
- Never copy secrets, tokens, raw Discord captures, private payloads, or provider credentials into docs, the agent map, or handoffs.
- Application settings use `CHARACTER_RELAY_*`; `ECHO_MASQUE_LIVE_*` names are workflow secrets, not runtime configuration.
