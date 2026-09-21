# Product and safety contracts

Source, schemas, migrations and tests establish implemented behavior. The accepted
[group-chat plan](../plans/discord-group-chat-core.md) establishes the next intended behavior;
its status and execution authorization are in [PROJECT_STATE.md](../../PROJECT_STATE.md).
Do not confuse design acceptance with deployed functionality.

For this initiative, explicit plan decisions supersede older requirements for automatic memory,
relationship simulation, fixed role-turn rules and Roast. They do not relax privacy, source
provenance, credentials, tool grants, delivery integrity or evaluation approval.

| Boundary | Reference |
| --- | --- |
| Current source and target ownership | [Architecture](../architecture.md) |
| Accepted group-chat behavior / acceptance | [Group-chat core plan](../plans/discord-group-chat-core.md) |
| Existing intelligence/source authority | [Intelligence v3](../intelligence-core-v3-architecture.md), [memory lifecycle](../memory-lifecycle-contract.md) |
| Authentication, privacy, credentials, Public Demo | [Security](../security.md), [Phase 15 evidence](../phase-15-security.md) |
| Discord scope and raw diagnostics | [Workspace](../discord-server-workspace.md), [debug capture](../discord-debug-capture.md) |
| Tools and durable operations | [MCP/jobs](../mcp-conversation-jobs.md), [HTTP targets](../http-target-contract.md) |
| Production storage | [Deployment](../railway-deployment.md), [storage safety](../storage-safety.md) |
| Portal and accessibility | [UI/UX](../ui-ux-contract.md), [components](../ui-component-library.md), [reference rules](../ui-page-migration-plan.md) |
| Time interpretation | [Server time](../server-timezone-runtime.md) |
| Evaluation approval and immutable evidence | [Authoring](../phase-16-authoring.md), [calibration](../phase-16-calibration.md), [release evidence](../phase-16-release.md) |

When migrating a boundary, update its specialized contract and proving tests in the same coherent
implementation phase. Do not silently claim the old code already satisfies the new design.
