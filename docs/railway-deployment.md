# Railway Deployment

Echo Masque deploys to Railway as one Docker service. The Docker build compiles the React client and the runtime serves both the web interface and FastAPI from the same public domain.

## Architecture

```text
Railway public domain
  -> Uvicorn / FastAPI
     -> /api/* and /health
     -> built React client from web/dist
  -> SQLite at /data/echo_masque.db
```

This deployment must stay at one replica because the MVP uses SQLite and process-memory provider credentials.

## 1. Create the service

1. In Railway, create a new project.
2. Choose **Deploy from GitHub repo**.
3. Select `wong001110/echo-masque` and the `main` branch.
4. Railway should detect the root `Dockerfile` and `railway.toml` automatically.
5. Do not set a custom start command. The Dockerfile reads Railway's injected `PORT` variable.

The repository configures `/health` as the deployment healthcheck and uses an on-failure restart policy.

## 2. Attach persistent storage

Add one Railway Volume to the service:

```text
Mount path: /data
```

The application database URL already defaults to:

```text
sqlite:////data/echo_masque.db
```

Without the volume, Character Cards, runs, reports, and evidence will be lost on redeploy.

Keep the service at exactly one replica. Multiple replicas cannot safely share this SQLite and in-memory runtime design.

## 3. Configure variables

The Docker image includes production-safe non-secret defaults:

```text
ECHO_MASQUE_ENVIRONMENT=production
ECHO_MASQUE_DEBUG=false
ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db
```

Optional Railway service variables:

```text
ECHO_MASQUE_LOG_LEVEL=INFO
ECHO_MASQUE_APP_NAME=Echo Masque
```

Do not define `PORT`; Railway supplies it automatically.

Provider API keys entered through the UI stay only in the running process and disappear after a restart. Do not put a paid provider key into a public deployment until access control is implemented.

## 4. Networking and region

1. Open the service **Settings** tab.
2. Under **Networking**, select **Generate Domain**.
3. When available on the selected Railway plan, choose the Southeast Asia / Singapore region.
4. Leave the service at one replica.

Railway routes the generated domain to the port used by the Docker container.

## 5. Validate the deployment

From a local checkout:

```bash
python scripts/railway_smoke.py https://your-service.up.railway.app
```

The smoke test verifies:

- `/health` returns Echo Masque metadata;
- the React interface is served from `/`;
- the deterministic Stable target exists;
- a real Benchmark Trial can start and finish;
- the Stable trial returns an expected passing score.

## 6. Enable GitHub-hosted smoke tests

After Railway generates the domain:

1. Open the GitHub repository settings.
2. Go to **Secrets and variables → Actions → Variables**.
3. Create a repository variable named `RAILWAY_PUBLIC_URL`.
4. Set it to the full Railway URL, including `https://`.
5. Open **Actions → Railway Smoke → Run workflow**.

The workflow uses only the public deterministic demo and does not require a provider key.

## 7. Persistence acceptance

Run a deterministic trial, redeploy the same Railway service, and confirm the prior run still appears. If data disappears, verify that the Volume is mounted at exactly `/data` before creating more records.

Railway Volumes are mounted as root. The production container runs as root so SQLite can write to the mounted path. This is a deployment-specific compromise for the current MVP and should be revisited when the application moves to a managed database.

## Security boundary

The current MVP has no production authentication. A public Railway domain should be treated as a demo environment:

- use Stable and Fragile deterministic cards for public testing;
- do not enter valuable provider credentials;
- do not store private character prompts or conversation data;
- disable or delete the public domain when it is not needed.

A later production phase should add authentication, per-user authorization, encrypted secret storage, rate limiting, and a managed database before real external users are invited.
