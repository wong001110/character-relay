# Railway deployment

Status: **supported production deployment guide**

Character Relay deploys as one Docker service. The root image builds the React Portal, and FastAPI serves both the Portal and `/api/*` from the same public domain.

```text
Railway domain
  -> FastAPI/Uvicorn + built Portal
  -> SQLite at /data/echo_masque.db

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

## 2. Attach persistent storage

Attach one Volume to the application service in the same Railway environment that owns the public domain:

```text
Mount path: /data
Database URL: sqlite:////data/echo_masque.db
```

A Volume in another environment/service does not protect Production. Attaching a new Volume also does not recover an older ephemeral database.

Production startup fails closed when SQLite is not under a mounted `/data` path. Keep one replica; do not share this SQLite topology across replicas.

## 3. Configure application settings

The runtime reads `CHARACTER_RELAY_*` application variables. Earlier product-prefix runtime variables are ignored.

Required production shape:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
CHARACTER_RELAY_AUTH_COOKIE_SECURE=true
CHARACTER_RELAY_LEGACY_LOCAL_USER_ENABLED=false
CHARACTER_RELAY_PUBLIC_REGISTRATION_ENABLED=false
CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL=<admin email>
CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<primary Fernet key>[,<older key>...]
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random connector secret>
RAILWAY_RUN_UID=0
```

Railway mounts Volumes as `root`. `RAILWAY_RUN_UID=0` allows the image entrypoint to repair ownership only under `/data`; it then immediately drops to the image user `character-relay` (UID `10001`) before starting Uvicorn. Do not set this variable for ordinary Docker/Compose runs, where the image already starts non-root. See Railway's [Volume permissions documentation](https://docs.railway.com/volumes#permissions).

Optional operational settings include:

```text
CHARACTER_RELAY_LOG_LEVEL=INFO
CHARACTER_RELAY_PUBLIC_DEMO_ENABLED=true
```

Do not define `PORT`. Keep passwords, Fernet keys, provider keys, Bot tokens, and connector secrets outside Git.

## 4. Bootstrap and authenticate Admin access

Configure the Bootstrap Admin email/password together and deploy. Sign in through the normal authentication flow; Admin routes, Storage & Backup, probes, and runtime administration use the authenticated HttpOnly Session and server-side role checks.

The Portal does not require an Admin Token or send `X-Echo-Admin`. Legacy token/header settings are not a production identity boundary.

After the first successful sign-in:

1. confirm non-Admin accounts cannot access Admin/runtime/trace surfaces;
2. keep the bootstrap credential unique and managed only through the deployment environment;
3. use invitations instead of enabling public registration unless open signup is an explicit product decision.

## 5. Configure provider credentials

Configure non-secret Provider/Base URL/Model/Prompt options through the appropriate Portal settings. Save persistent credentials through the encrypted Credential Vault.

Optional server-side environment fallbacks use settings such as:

```text
CHARACTER_RELAY_ADAPTIVE_API_KEY=<limited provider key>
CHARACTER_RELAY_JUDGE_API_KEY=<limited provider key>
CHARACTER_RELAY_AUTHORING_API_KEY=<limited provider key>
```

Character provider credentials are owner-scoped Vault records. API responses and exports expose status/source metadata only. Prefer separate, revocable, spending-limited keys for production and Demo workloads.

## 6. Deploy the Discord Connector

Deploy `connectors/discord/Dockerfile` as a separate worker/service and follow `connectors/discord/README.md`.

The Connector and application must share the same long random connector secret. Keep the Discord Bot token and connector secret only in their service environments; never place them in Portal configuration, logs, docs, or artifacts.

## 7. Validate availability

Run the credential-free smoke against the deployed application:

```bash
python scripts/railway_smoke.py https://your-service.up.railway.app
```

Then run the relevant GitHub Actions smoke/live acceptance workflows. Live workflows use repository secret names such as `ECHO_MASQUE_LIVE_*`; those are workflow inputs, not Character Relay runtime configuration.

Credential-free smoke proves availability, not persistence, account isolation, provider readiness, Connector delivery, or Demo reconciliation.

## 8. Verify storage across a redeploy

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

## 9. Back up and restore

Export a secret-free account/workspace archive before migrations or infrastructure changes. Exports intentionally omit raw/encrypted credentials, Sessions, password hashes, invitation codes, Bot tokens, and connector secrets.

Test imports in a disposable environment. Use Replace mode only with a verified separate backup and the exact intended owner scope.

## 10. Release acceptance

Before exposing a new release:

- verify authentication, Admin role, two-account isolation, and Demo read-only boundaries;
- verify Vault readiness/rotation and recursive redaction;
- run Python, Portal, Connector, Docker, Railway, and task-relevant live checks;
- confirm Public Demo reconciliation/status when enabled;
- verify one replica and `/data` persistence;
- confirm Railway has `RAILWAY_RUN_UID=0` and the running Uvicorn process has dropped to UID `10001`;
- review artifacts/job summaries without copying secret values.

See `docs/storage-safety.md`, `docs/phase-15-security.md`, `docs/security.md`, and `docs/manual-validation.md`.
