# Production Storage Safety

## PostgreSQL production target (Knowledge Fabric Phase 1)

New Knowledge Fabric production deployments use PostgreSQL with the `vector`
extension. Application startup takes an advisory transaction lock, runs
`CREATE EXTENSION IF NOT EXISTS vector`, and records the `database-foundation-v1`
revision. The database user must have exactly the privilege needed for that
bootstrap, or the extension must be installed by the platform operator before the
application starts.

PostgreSQL health intentionally reports `database_kind: "postgresql"` but never a
connection host, database name, filesystem path, user, or credential. Database
durability is verified through the provider's backup/restore controls plus the
same application Persistence Probe described below.

Use `scripts/migrate_sqlite_to_postgres.py` only with a stopped/quiet SQLite
source, a retained source backup, an empty PostgreSQL target, and no application
instance connected to that target. It creates a separate consistent SQLite snapshot
for the transfer, will not merge data into a populated/unknown target, and will not
delete or mutate the original source. The target's `running`/`failed` migration ledger
blocks normal startup until the operator completes the copy or uses a fresh target.
See `docs/railway-deployment.md` for the exact migration sequence.

## SQLite migration source

SQLite can be retained as an offline input to `scripts/migrate_sqlite_to_postgres.py`,
but it is not a running production authority. Production startup rejects every SQLite
URL before opening the database.

## Why data disappeared

A Live Demo seed successfully created Character Cards, Scenarios, a Test Pack, and Runs. The next Railway deployment returned an empty workspace. Re-running the idempotent seed generated different UUIDs for every named object. This proves that the new deployment opened a new SQLite database rather than reusing the previous database.

The application did not delete these records. Startup cleanup removes only the two legacy fixed Character Card IDs:

```text
card-stable-ann
card-fragile-ann
```

## Fail-closed startup guard

Production startup rejects SQLite with a safe error before opening the database. This
prevents a Knowledge Fabric deployment from silently treating a local or mounted file
as a parallel production authority.

## Health verification

A healthy deployed version exposes non-secret storage metadata at `/health`:

```json
{
  "environment": "production",
  "storage": {
    "database_kind": "sqlite",
    "database_path": "/data/echo_masque.db",
    "persistent_required": true,
    "mount_path": "/data",
    "mount_ready": true,
    "storage_instance_id": "stable-uuid"
  }
}
```

Before and after every Railway redeploy, compare `storage_instance_id`.

- Same ID: the deployment reused the same database.
- Different ID: the deployment opened a different database.
- Missing storage block: the old application version is still serving.
- New deployment fails startup: fix the Production Volume attachment before retrying.

## Persistence acceptance

1. Record the current `storage_instance_id`.
2. Create a Persistence Probe in **Workspace → Storage & Backup**.
3. Create one temporary Character Card.
4. Redeploy the same Production service.
5. Confirm the new `/health` reports the same `storage_instance_id`.
6. Confirm the Probe and Character Card remain.
7. Delete only the temporary Probe/Card after verification.

## Backup boundary

Before infrastructure changes, export the Workspace JSON archive from **Storage & Backup**. The archive includes cards, Scenarios, Test Packs, snapshotted Runs, evidence, and non-secret Admin configuration. It excludes Subject, Adaptive, Judge, and Admin credentials.

## Startup migration safety

The Intelligence Core v3 hard-cutover keeps a dedicated persistent ledger. A completed ledger entry
prevents a later restart from repeating the migration; a failed or interrupted entry is retried on
the next startup using the migration's deterministic, repeat-safe projections. The ledger records
only state and a safe exception type, never raw data or exception messages.

Before migration, take the Workspace export and preserve the SQLite file/Volume. SQLite
foreign-key checks are enabled on every connection. A legacy-table rebuild is followed by
`foreign_key_check`; if it reports an existing orphan, repair or restore the source before retrying
the offline migration.
