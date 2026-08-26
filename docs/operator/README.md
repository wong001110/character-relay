# Operator guide

This section is for the person running Character Relay and its Discord Connector.

## Production path

1. Review the [security and privacy boundary](../security.md).
2. Deploy the API/Portal using the [Railway guide](../railway-deployment.md).
3. Run Knowledge Fabric on PostgreSQL + pgvector; SQLite is only a local development/test or migration source. Follow [storage safety](../storage-safety.md).
4. Configure and deploy the Discord worker using the [Discord setup guide](../user/discord-setup.md) and [Connector reference](../../connectors/discord/README.md).
5. Run the [manual validation checklist](../manual-validation.md).

## Operational entry points

- Discord incidents: [user-friendly debugging flow](../user/discord-debugging.md), then the [raw-capture privacy contract](../discord-debug-capture.md).
- Authentication, credentials, owner isolation, and Public Demo: [security](../security.md) and [Phase 15 security contract](../phase-15-security.md).
- Backup, restore, migrations, and persistence probes: [storage safety](../storage-safety.md).
- Runtime/provider traces: [provider tracing](../provider-tracing.md).
- Server workspace configuration: [Discord Server Workspace](../discord-server-workspace.md).

Never put production secrets or revealed Discord capture content in repository files, OpenWiki output, CI artifacts, or support tickets.
