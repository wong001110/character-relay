# Canonical contracts

These documents define current product or architecture boundaries. Source, schemas/types, migrations, and tests remain the strongest evidence of implemented behavior.

| Boundary | Canonical reading |
| --- | --- |
| Service ownership and data authority | [Architecture](../architecture.md) |
| Intelligence/runtime authority and no-Topic cutover | [Intelligence Core v3](../intelligence-core-v3-architecture.md) |
| Authentication, credentials, privacy, Public Demo | [Security](../security.md), [Phase 15 security](../phase-15-security.md) |
| Discord Server scope and deployments | [Discord Server Workspace](../discord-server-workspace.md) |
| Temporary raw Discord debugging | [Discord debug capture](../discord-debug-capture.md) |
| Production topology and persistence | [Railway deployment](../railway-deployment.md), [storage safety](../storage-safety.md) |
| Portal behavior and composition | [UI/UX contract](../ui-ux-contract.md), [component library](../ui-component-library.md), [page migration plan](../ui-page-migration-plan.md) |
| External HTTP targets | [HTTP target contract](../http-target-contract.md) |
| Server-local time | [Server timezone runtime](../server-timezone-runtime.md) |
| Evaluation approval and calibration | [Evaluation authoring](../phase-16-authoring.md), [calibration](../phase-16-calibration.md), [release acceptance](../phase-16-release.md) |

Subsystem documents such as Context/RAG, media epistemics, provider tracing, Smart Output, and tool calling apply only where current source/tests still implement their stated boundary. If a contract and implementation conflict, surface the conflict; do not manufacture compatibility behavior.
