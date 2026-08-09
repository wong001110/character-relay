# Railway Deployment

Echo Masque deploys to Railway as one Docker service. The Docker build compiles the React client and the runtime serves both the web interface and FastAPI from the same public domain.

## Architecture

```text
Railway public domain
  -> Uvicorn / FastAPI
     -> /api/* and /health
     -> built React client from web/dist
  -> SQLite at /data/echo_masque.db
     -> Character Cards
     -> Custom Scenarios and Test Packs
     -> immutable Run snapshots and Experiment History
     -> reports, evidence, and Admin non-secret profiles
  -> Admin-managed Adaptive Tester and Semantic Judge
     -> credentials from Railway environment variables
```

Keep one replica. The current implementation uses SQLite plus process-memory Subject credentials and optional Admin credential overrides.

## 1. Create the service

1. In Railway, create a new project.
2. Choose **Deploy from GitHub repo**.
3. Select `wong001110/character-relay` and the `main` branch.
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

Without the volume, user Character Cards, Scenarios, Test Packs, Admin non-secret runtime profiles, snapshotted Trials, reports, and evidence disappear on redeploy.

Creating or attaching a Volume does not copy a database from an older ephemeral container into `/data`. Records created before the service started using the mounted path may already be unrecoverable.

Keep exactly one replica. Multiple replicas cannot safely share the current SQLite and process-memory runtime design.

## 3. Configure variables

Character Relay application settings use the `CHARACTER_RELAY_*` namespace. Previous product-prefix application variables are not read by the runtime.

The image includes these non-secret defaults:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DEBUG=false
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
```

Recommended operational variables:

```text
CHARACTER_RELAY_LOG_LEVEL=INFO
CHARACTER_RELAY_APP_NAME=Character Relay
```

Do not define `PORT`; Railway supplies it.

### Admin access

Production Admin APIs are disabled until this variable exists:

```text
CHARACTER_RELAY_ADMIN_TOKEN=<long-random-admin-token>
```

The browser sends the value through `X-Echo-Admin`. Admin Settings and Workspace Storage tools store it only in browser `sessionStorage`, so closing the browser session clears it.

Do not reuse a Provider API key as the Admin token.

### Shared Adaptive Tester

Configure the non-secret Provider, Base URL, Model, Prompt, Temperature, and maximum turns through **Admin Settings**. Store the persistent production credential in Railway:

```text
CHARACTER_RELAY_ADAPTIVE_API_KEY=<provider-key-for-adaptive-tester>
```

### Shared Semantic Judge

Configure the non-secret Provider, Base URL, Model, Prompt, Temperature, rubric version, and default Judge Mode through **Admin Settings**. Store the persistent production credential in Railway:

```text
CHARACTER_RELAY_JUDGE_API_KEY=<provider-key-for-semantic-judge>
```

The Adaptive and Judge keys may be the same limited test key during MVP evaluation, but separate keys make cost attribution and rotation clearer.

Keys entered directly in Admin Settings are process-memory overrides. They disappear after a Railway restart or redeploy. Railway variables are the persistent source.

Raw Admin runtime keys are never written to SQLite, Character Cards, Trial events, Lab Notes, JSON reports, Run snapshots, workspace archives, or application logs.

### Subject model credentials

A Subject key entered while creating or reconnecting a Prompt + Model Character Card stays only in the running process. It disappears after restart unless the target uses its configured environment fallback. Do not place high-value unrestricted keys in the public demo.

## 4. Networking and region

1. Open the service **Settings** tab.
2. Under **Networking**, select **Generate Domain**.
3. Choose Southeast Asia / Singapore when available on the Railway plan.
4. Leave the service at one replica.

## 5. Validate application availability

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

This test proves that the current deployment is available. It does not prove that the same database will survive the next deployment.

## 6. Validate Admin Runtime

After setting `CHARACTER_RELAY_ADMIN_TOKEN`:

1. Open **Admin Settings**.
2. Enter the Admin token.
3. Enable Adaptive Tester and Semantic Judge.
4. Configure their non-secret Provider profiles.
5. Confirm their status reports `environment` as the credential source after setting the two Railway keys.
6. Run one Adaptive + Hybrid Trial or Test Pack.
7. Redeploy the service.
8. Confirm Admin profiles persist and both runtimes return to Ready without re-entering API keys.

Expected persistence:

```text
Admin Provider/Model/Prompt settings -> persist in /data SQLite
Railway Adaptive/Judge keys          -> remain Railway variables
Process-memory override keys          -> cleared on restart
Subject card credentials              -> cleared unless environment-backed
```

## 7. Storage Diagnostics

Open **Workspace → Storage & Backup** and enter the Admin Token.

For the Railway deployment, the expected values are:

```text
Environment: production
Database kind: sqlite
Database path: /data/echo_masque.db
Writable: Yes
Persistent path: Yes
Warning: none
```

The page also shows Character, Scenario, Test Pack, and snapshotted Run counts plus the last workspace write timestamp.

A Volume card in Railway only confirms the resource is attached. Storage Diagnostics confirms that the running application actually resolved SQLite to the mounted path and can write there.

## 8. Persistence probe across a redeploy

The persistence probe is the required acceptance test:

1. Open **Workspace → Storage & Backup**.
2. Create a persistence probe.
3. Copy the returned probe ID.
4. In Railway, redeploy the service or deploy a new commit.
5. Wait for `/health` and Railway deployment status to become healthy.
6. Return to Storage & Backup.
7. Enter the same Admin Token.
8. Check the saved probe ID.
9. Confirm its marker and creation time are unchanged.
10. Delete the probe.

Interpretation:

```text
Probe survives -> the new deployment opened the same persistent database
Probe missing  -> the new deployment opened a different or ephemeral database
```

Do not treat “Volume attached” or “database path looks correct” as a substitute for this cross-deployment probe.

## 9. Workspace backup and restore

Before significant Railway changes, export the workspace from **Storage & Backup**.

The archive includes:

- user-owned Targets and Character Cards;
- Custom Scenarios and versioned Test Packs;
- immutable Run snapshots;
- Trial records, turns, events, evidence, and reports;
- non-secret Admin Runtime configuration.

It excludes:

- Admin Token;
- Subject API keys;
- Adaptive Tester API key;
- Semantic Judge API key;
- authorization headers and other redacted credentials.

Import modes:

- **Merge** keeps existing IDs and skips duplicates.
- **Replace** deletes the current owner's workspace before importing. Retain a separate export before using it.

## 10. GitHub-hosted smoke tests

The Railway Smoke workflow targets:

```text
https://echo-masque-production.up.railway.app
```

It runs for pull requests, updates to `main`, and manual workflow dispatch. The workflow retries while Railway finishes a rollout.

The GitHub smoke remains credential-free and does not trigger a production redeploy around a probe. The human persistence probe therefore remains a separate required check.

## Security boundary

Admin Runtime configuration, storage diagnostics, probes, and workspace portability are token-protected, but the application still lacks production user authentication and authorization. A public deployment remains a controlled demo environment:

- use a long random Admin token;
- use limited, revocable Provider test keys;
- set Provider spending limits where available;
- do not store private Character Cards or sensitive transcripts;
- do not invite untrusted external users;
- disable the public domain when it is not needed.

A production phase should add authenticated users, role-based Admin access, encrypted secret storage, rate limiting, managed persistence, audit logs, and abuse controls.
