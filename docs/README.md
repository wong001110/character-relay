# Character Relay documentation

## Current development entry

**[AGENTS.md](../AGENTS.md) -> [PROJECT_STATE.md](../PROJECT_STATE.md) ->
[active group-chat plan](plans/discord-group-chat-core.md) -> [architecture/source map](architecture.md).**

The group-chat simplification is accepted design, not completed functionality. This documentation
PR changes no runtime behavior. Current progress and Work's exact next action live only in
PROJECT_STATE.md. Other branch plans are not active unless that state explicitly selects them.

| Reader | Entry |
| --- | --- |
| Product user | [User guide](user/README.md) |
| Operator / incident responder | [Operator guide](operator/README.md) |
| Developer / Work | [Developer setup and checks](developer/README.md) |
| Product/security reviewer | [Canonical contracts](contracts/README.md) |
| Prior implementation evidence | [Historical/reference index](history/README.md) |

## Authority

Current user authorization bounds the task. Source, schemas, migrations and tests prove existing
behavior. The accepted active plan defines intended changes and supersedes conflicting old designs
for those changes; unrelated security/evaluation/production invariants remain. Neither a roadmap,
old checked box, PR description nor generated text proves implementation or live readiness.

The former agent-map, handoff, workflow and active-development-plan pages are link-only compatibility
paths. They contain no second development process or current phase state. Do not recreate them as
parallel authorities. No generated wiki is part of the development bootstrap.

## Product and operational references

- [Discord setup](user/discord-setup.md), [debugging](user/discord-debugging.md),
  [server workspace](discord-server-workspace.md), [debug capture](discord-debug-capture.md).
- [Security](security.md), [storage safety](storage-safety.md),
  [Railway deployment](railway-deployment.md), [MCP and jobs](mcp-conversation-jobs.md).
- [Existing Intelligence v3 contract](intelligence-core-v3-architecture.md),
  [memory lifecycle](memory-lifecycle-contract.md), [Knowledge Fabric](knowledge-fabric-architecture.md).
  These describe existing boundaries; older automatic/social target designs yield to the active plan.
- [Portal development](portal-development.md), [UI/UX](ui-ux-contract.md),
  [components](ui-component-library.md), [UI reference rules](ui-page-migration-plan.md).
- [Manual validation](manual-validation.md), [mutation testing](mutation-testing.md).

Discord is the supported production connector. Legacy Telegram/WhatsApp records are not supported
runtimes. Retired Topic authority, Topic-scoped memory and Topic-driven Wiki are not restored.

## Evaluation and calibration

Retain the product's offline evaluation capability and approval/evidence boundaries:
[Experiment Matrix](phase-14-experiment-matrix.md), [authoring](phase-16-authoring.md),
[AI-assisted drafts](phase-16-ai-authoring.md), [calibration](phase-16-calibration.md),
[rubric coverage](phase-16-rubric-coverage.md), [release evidence](phase-16-release.md).
These are not a requirement to run a judge for every ordinary Discord reply.

## Maintenance

Update only affected policy, state, plan or ownership. Specialized operational and historical docs
can remain when still useful, but cannot revive a retired runtime or old execution workflow. Keep
status truthful while implementation migrates. Never put raw private captures or secrets in docs.
