# Railway Deployment

Echo Masque deploys to Railway as one Docker service. The Docker build compiles the React client and the runtime serves both the web interface and FastAPI from the same public domain.

## Architecture

```text
Railway public domain
  -> Uvicorn / FastAPI
     -> /api/* and /health
     -> built React client from web/dist
  -> SQLite at /data/echo_masque.db
  -> Admin-managed Adaptive Tester and Semantic Judge
     -> non-secret profiles in SQLite
     -> credentials from Railway environment variables
```

Keep one replica. The current implementation uses SQLite plus process-memory Subject credentials and optional Admin credential overrides.

## 1. Create the service

1. In Railway, create a new project.
2. Choose **Deploy from GitHub repo**.
3. Select `wong001110/echo-masque` and the `main` branch.
4. Railway should detect the root `Dockerfile` and `railway.toml` automatically.
5. Do not set a custom start command. The Dockerfile reads Railway's injected `PORT` variable.

The repository configures `/health` as the deployment health check and uses an on-failure restart policy.

## 2. Attach persistent storage

Add one Railway Volume:

```text
Mount path: /data
```

The production database path is:

```text
sqlite:////data/echo_masque.db
```

Without the volume, user Character Cards, Admin non-secret runtime profiles, Trials, reports, and evidence disappear on redeploy.

Keep exactly one replica. Multiple replicas cannot safely share the current SQLite and process-memory runtime design.

## 3. Configure variables

The image includes these non-secret defaults:

```text
ECHO_MASQUE_ENVIRONMENT=production
ECHO_MASQUE_DEBUG=false
ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db
```

Recommended operational variables:

```text
ECHO_MASQUE_LOG_LEVEL=INFO
ECHO_MASQUE_APP_NAME=Echo Masque
```

Do not define `PORT`; Railway supplies it.

### Admin access

Production Admin APIs are disabled until this variable exists:

```text
ECHO_MASQUE_ADMIN_TOKEN=<long-random-admin-token>
```

The browser sends the value through `X-Echo-Admin`. Admin Settings stores it only in browser `sessionStorage`, so closing the browser session clears it.

Do not reuse a Provider API key as the Admin token.

### Shared Adaptive Tester

Configure the non-secret Provider, Base URL, Model, Prompt, Temperature, and maximum turns through **Admin Settings**. Store the persistent production credential in Railway:

```text
ECHO_MASQUE_ADAPTIVE_API_KEY=<provider-key-for-adaptive-tester>
```

### Shared Semantic Judge

Configure the non-secret Provider, Base URL, Model, Prompt, Temperature, rubric version, and default Judge Mode through **Admin Settings**. Store the persistent production credential in Railway:

```text
ECHO_MASQUE_JUDGE_API_KEY=<provider-key-for-semantic-judge>
```

The Adaptive and Judge keys may be the same limited test key during MVP evaluation, but separate keys make cost attribution and rotation clearer.

Keys entered directly in Admin Settings are process-memory overrides. They disappear after a Railway restart or redeploy. Railway variables are the persistent source.

Raw Admin runtime keys are never written to SQLite, Character Cards, Trial events, Lab Notes, JSON reports, or application logs.

### Subject model credentials

A Subject key entered while creating or reconnecting a Prompt + Model Character Card stays only in the running process. It disappears after restart unless the target uses its configured environment fallback. Do not place high-value unrestricted keys in the public demo.

## 4. Networking and region

1. Open the service **Settings** tab.
2. Under **Networking**, select **Generate Domain**.
3. Choose Southeast Asia / Singapore when available on the Railway plan.
4. Leave the service at one replica.

## 5. Validate the deployment

```bash
python scripts/railway_smoke.py https://your-service.up.railway.app
```

The credential-free smoke test verifies:

- `/health` returns Echo Masque metadata;
- the React interface is served from `/`;
- the internal Stable target exists;
- English and Simplified Chinese Rules-mode Benchmark Trials complete;
- test and scenario languages remain correct;
- Stable scores meet the passing threshold.

The deployment smoke does not call Adaptive Tester or Semantic Judge and therefore does not spend Provider credits.

## 6. Validate Admin Runtime

After setting `ECHO_MASQUE_ADMIN_TOKEN`:

1. Open **Admin Settings**.
2. Enter the Admin token.
3. Enable Adaptive Tester and Semantic Judge.
4. Configure their non-secret Provider profiles.
5. Confirm their status reports `environment` as the credential source after setting the two Railway keys.
6. Run one Adaptive + Hybrid Trial.
7. Redeploy the service.
8. Confirm Admin profiles persist and both runtimes return to Ready without re-entering API keys.

Expected persistence:

```text
Admin Provider/Model/Prompt settings -> persist in /data SQLite
Railway Adaptive/Judge keys          -> remain Railway variables
Process-memory override keys          -> cleared on restart
Subject card credentials              -> cleared unless environment-backed
```

## 7. GitHub-hosted smoke tests

The Railway Smoke workflow targets:

```text
https://echo-masque-production.up.railway.app
```

It runs for pull requests, updates to `main`, and manual workflow dispatch. The workflow retries while Railway finishes a rollout.

## 8. Persistence acceptance

Create a user-owned Character Card and complete a Rules-mode Trial. Redeploy and confirm the card, Trial, evidence, reports, and Admin non-secret settings survive. If data disappears, confirm the Volume is mounted at exactly `/data`.

Railway Volumes are mounted as root. The production container currently runs as root so SQLite can write to the mounted path. Revisit this when moving to a managed database.

## Security boundary

Admin Runtime configuration is token-protected, but the application still lacks production user authentication and authorization. A public deployment remains a controlled demo environment:

- use a long random Admin token;
- use limited, revocable Provider test keys;
- set Provider spending limits where available;
- do not store private Character Cards or sensitive transcripts;
- do not invite untrusted external users;
- disable the public domain when it is not needed.

A production phase should add authenticated users, role-based Admin access, encrypted secret storage, rate limiting, managed persistence, audit logs, and abuse controls.
