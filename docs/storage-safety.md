# Production Storage Safety

Echo Masque uses SQLite for its current Railway deployment. A database path that looks correct is not enough: `/data/echo_masque.db` is persistent only when `/data` is an actual Railway Volume mount in the active Production environment.

## Why data disappeared

A Live Demo seed successfully created Character Cards, Scenarios, a Test Pack, and Runs. The next Railway deployment returned an empty workspace. Re-running the idempotent seed generated different UUIDs for every named object. This proves that the new deployment opened a new SQLite database rather than reusing the previous database.

The application did not delete these records. Startup cleanup removes only the two legacy fixed Character Card IDs:

```text
card-stable-ann
card-fragile-ann
```

## Environment-scoped Railway Volume

Railway Volumes are scoped to an environment. A Volume visible elsewhere in the project does not protect the public Production deployment.

Verify all of the following in Railway:

1. Select the environment that owns `https://echo-masque-production.up.railway.app`.
2. Confirm the environment is **Production**.
3. Open the exact `echo-masque` service that owns that public domain.
4. Confirm a Volume is attached to that service in the same environment.
5. Confirm the mount path is exactly:

```text
/data
```

6. Confirm the service variable is exactly:

```text
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
RAILWAY_RUN_UID=0
```

Railway mounts the Volume as `root`. The root image's entrypoint uses this platform override only to repair `/data` ownership, then drops to the non-root `character-relay` user (UID `10001`) before starting Uvicorn. Ordinary Docker/Compose runs do not need `RAILWAY_RUN_UID`.

7. Keep one replica while using SQLite.

## Fail-closed startup guard

Production startup now requires all of the following:

- backend is SQLite;
- database file resolves under `/data`;
- `/data` is a real filesystem mount point;
- the database can initialize;
- a persistent Storage Instance ID can be read or created.

When `/data` is only the image-local directory created by the Dockerfile, startup raises:

```text
Unsafe production storage: /data exists but is not a mounted persistent volume.
```

The deployment must not become healthy. This prevents Railway from silently replacing a working deployment with a new empty SQLite database.

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
