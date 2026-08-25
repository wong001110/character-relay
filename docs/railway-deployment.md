# Railway deployment

Status: **supported production deployment guide**

Character Relay deploys as one Docker service. The root image builds the React Portal, and FastAPI serves both the Portal and `/api/*` from the same public domain.

> Knowledge Fabric Phase 1 adds the supported PostgreSQL + pgvector foundation and an
> explicit SQLite-to-PostgreSQL migration tool. Existing SQLite deployments remain
> supported only while they are migrated; new production Knowledge Fabric work must
> use PostgreSQL with the `vector` extension. Do not point two application replicas
> at SQLite during this transition.

```text
Railway domain
  -> FastAPI/Uvicorn + built Portal
  -> PostgreSQL + pgvector (target production topology)
  -> SQLite at /data/echo_masque.db (temporary migration source only)

Discord Gateway
  -> separately deployed connectors/discord worker
  -> authenticated connector API
```

Keep exactly one application replica while SQLite is the production database.

## 1. Create the application service

1. Create a Railway service from this repository's `main` branch.
2. Use the root `Dockerfile` and `railway.toml`; do not add a custom start command.
3. Generate a public domain for the service.
4. Keep the service at one replica.

Railway supplies `PORT`. The configured health endpoint is `/health`.

## 2. Provision PostgreSQL + pgvector and migrate safely

Create an empty PostgreSQL database whose operator permits:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The application performs that idempotent bootstrap at startup and records the
`database-foundation-v1` revision. Treat a failure as a database provisioning
problem; do not remove the extension requirement or fall back silently to a
different vector backend.

For an existing SQLite deployment:

1. Export the normal secret-free Workspace archive and retain the original Railway
   Volume as a rollback source.
2. Stop writes to the SQLite service, keep the PostgreSQL application service stopped, and make a database-volume backup.
3. From a trusted one-off environment that can read the SQLite file and connect to
   the empty PostgreSQL database, run:

   ```bash
   python scripts/migrate_sqlite_to_postgres.py \
     --source-url sqlite:////data/echo_masque.db \
     --target-url 'postgresql+psycopg://<user>:<password>@<host>:5432/<database>'
   ```

   The tool creates a unique, SQLite-native consistent snapshot (including committed
   WAL content) and copies only that snapshot. It fingerprints the snapshot,
   refuses a non-empty or unexpectedly populated PostgreSQL target, preserves source
   IDs/sequences, records a completed ledger, and never deletes or mutates the
   original SQLite source. It requires the source to already have the current,
   completed Intelligence schema with no legacy tables containing data; update a
   verified source copy before running the cross-database transfer.
   While its ledger is `running` or `failed`, normal application startup against the
   PostgreSQL target fails closed; do not use the target for other application work
   during the copy.
4. Start one application instance against the PostgreSQL URL only after the tool
   reports `completed`, check `/health`, and
   verify sign-in, a persisted Probe, and the copied Workspace data before switching
   the public service variable.
5. Keep the SQLite Volume until the PostgreSQL backup/restore and application
   acceptance checks have succeeded. A completed copy is idempotent only for that
   same source/target ledger; use a fresh target for another import.

The Docker image's SQLite default remains for local compatibility during this
branch. On Railway, explicitly override it with the PostgreSQL connection URL:

```text
CHARACTER_RELAY_DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
```

Never commit the URL or expose it through Portal configuration, health output,
traces, exports, or logs.

## 3. Temporary SQLite storage during migration

Attach one Volume to the application service in the same Railway environment that owns the public domain:

```text
Mount path: /data
Database URL: sqlite:////data/echo_masque.db
```

A Volume in another environment/service does not protect Production. Attaching a new Volume also does not recover an older ephemeral database.

Production startup fails closed when SQLite is not under a mounted `/data` path. Keep one replica; do not share this SQLite topology across replicas.

## 4. Configure application settings

The runtime reads `CHARACTER_RELAY_*` application variables. Earlier product-prefix runtime variables are ignored.

Required PostgreSQL production shape:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
CHARACTER_RELAY_AUTH_COOKIE_SECURE=true
CHARACTER_RELAY_LEGACY_LOCAL_USER_ENABLED=false
CHARACTER_RELAY_PUBLIC_REGISTRATION_ENABLED=false
CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL=<admin email>
CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<primary Fernet key>[,<older key>...]
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random connector secret>
RAILWAY_RUN_UID=0
```

`RAILWAY_RUN_UID=0` is needed only while the service mounts the temporary SQLite
Volume. It allows the entrypoint to repair ownership only under `/data`, then it
immediately drops to the image user `character-relay` (UID `10001`) before starting
Uvicorn. Do not set it for an ordinary PostgreSQL deployment with no `/data` mount.
See Railway's [Volume permissions documentation](https://docs.railway.com/volumes#permissions).

Optional operational settings include:

```text
CHARACTER_RELAY_LOG_LEVEL=INFO
CHARACTER_RELAY_PUBLIC_DEMO_ENABLED=true
```

Do not define `PORT`. Keep passwords, Fernet keys, provider keys, Bot tokens, and connector secrets outside Git.

### Knowledge Fabric private artifact storage

Phase 3 uses a private Cloudflare R2 bucket for original Knowledge Fabric source artifacts. The
application uses the S3-compatible API only; AWS S3 is an explicit supported alternative, not a
public download path. Configure the bucket and credentials only in the service environment:

```text
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_PROVIDER=cloudflare_r2
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_BUCKET=<private-bucket-name>
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_ACCESS_KEY_ID=<R2 access key ID>
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_SECRET_ACCESS_KEY=<R2 secret access key>
CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_PREFIX=knowledge-fabric
```

For AWS S3, set `..._PROVIDER=aws_s3`, the private bucket, access key and secret, and a required
`CHARACTER_RELAY_KNOWLEDGE_OBJECT_STORAGE_REGION`; an S3-compatible private endpoint is optional.
Do not put these values in Portal settings, source-adapter credentials, exports, traces, logs, or
fixtures. The application stores only provider, bucket, object key, hash, size, and content type;
it does not generate public object URLs or ACLs.

## 5. Bootstrap and authenticate Admin access

Configure the Bootstrap Admin email/password together and deploy. Sign in through the normal authentication flow; Admin routes, Storage & Backup, probes, and runtime administration use the authenticated HttpOnly Session and server-side role checks.

The Portal does not require an Admin Token or send `X-Echo-Admin`. Legacy token/header settings are not a production identity boundary.

After the first successful sign-in:

1. confirm non-Admin accounts cannot access Admin/runtime/trace surfaces;
2. keep the bootstrap credential unique and managed only through the deployment environment;
3. use invitations instead of enabling public registration unless open signup is an explicit product decision.

## 6. Configure provider credentials

Configure non-secret Provider/Base URL/Model/Prompt options through the appropriate Portal settings. Save persistent credentials through the encrypted Credential Vault.

Optional server-side environment fallbacks use settings such as:

```text
CHARACTER_RELAY_ADAPTIVE_API_KEY=<limited provider key>
CHARACTER_RELAY_JUDGE_API_KEY=<limited provider key>
CHARACTER_RELAY_AUTHORING_API_KEY=<limited provider key>
```

Character provider credentials are owner-scoped Vault records. API responses and exports expose status/source metadata only. Prefer separate, revocable, spending-limited keys for production and Demo workloads.

## 7. Deploy the Discord Connector

Deploy `connectors/discord/Dockerfile` as a separate worker/service and follow `connectors/discord/README.md`.

The Connector and application must share the same long random connector secret. Keep the Discord Bot token and connector secret only in their service environments; never place them in Portal configuration, logs, docs, or artifacts.

## 8. Validate availability

Run the credential-free smoke against the deployed application:

```bash
python scripts/railway_smoke.py https://your-service.up.railway.app
```

Then run the relevant GitHub Actions smoke/live acceptance workflows. Live workflows use repository secret names such as `ECHO_MASQUE_LIVE_*`; those are workflow inputs, not Character Relay runtime configuration.

Credential-free smoke proves availability, not persistence, account isolation, provider readiness, Connector delivery, or Demo reconciliation.

## 9. Verify storage across a redeploy

Before deployment, record the non-secret storage metadata from `/health`, including `storage_instance_id`.

1. Sign in as an Admin and open **Storage & Backup**.
2. Create a Persistence Probe and retain its ID.
3. Redeploy the same Railway service.
4. Confirm `/health` is healthy and reports the same `storage_instance_id`.
5. Confirm the saved Probe remains, then delete the temporary Probe.

Interpretation:

- same ID and retained Probe: the deployment reused the database;
- different/missing ID or Probe: stop and investigate the environment/service/Volume attachment;
- startup failure: restore the required `/data` mount before retrying.

## 10. Back up and restore

Export a secret-free account/workspace archive before migrations or infrastructure changes. Exports intentionally omit raw/encrypted credentials, Sessions, password hashes, invitation codes, Bot tokens, and connector secrets.

Test imports in a disposable environment. Use Replace mode only with a verified separate backup and the exact intended owner scope.

## 11. Release acceptance

Before exposing a new release:

- verify authentication, Admin role, two-account isolation, and Demo read-only boundaries;
- verify Vault readiness/rotation and recursive redaction;
- run Python, Portal, Connector, Docker, Railway, and task-relevant live checks;
- confirm Public Demo reconciliation/status when enabled;
- verify PostgreSQL backup/restore and pgvector extension availability; if still in the
  temporary SQLite migration topology, verify one replica and `/data` persistence;
- if using the temporary SQLite Volume, confirm Railway has `RAILWAY_RUN_UID=0` and
  the running Uvicorn process has dropped to UID `10001`;
- review artifacts/job summaries without copying secret values.

See `docs/storage-safety.md`, `docs/phase-15-security.md`, `docs/security.md`, and `docs/manual-validation.md`.
