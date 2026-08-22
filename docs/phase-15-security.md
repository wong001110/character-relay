# Phase 15 — Authentication, User Isolation, and Secure Credential Vault

Phase 15 changes Echo Masque from a trusted single-workspace deployment into a session-authenticated multi-user service.

## Production environment

Configure these Railway variables before enabling the account UI:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
CHARACTER_RELAY_LEGACY_LOCAL_USER_ENABLED=false
CHARACTER_RELAY_PUBLIC_REGISTRATION_ENABLED=false
CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL=<admin email>
CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<Fernet key>
```

Generate the first encryption key locally:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the key outside Git and backups. The application cannot recover encrypted credentials without at least one matching key.

Optional quota variables include:

```text
CHARACTER_RELAY_REQUEST_LIMIT_PER_MINUTE=300
CHARACTER_RELAY_LOGIN_FAILURE_LIMIT=5
CHARACTER_RELAY_LOGIN_FAILURE_WINDOW_SECONDS=900
CHARACTER_RELAY_LOGIN_BLOCK_SECONDS=900
CHARACTER_RELAY_MAX_CHARACTERS_PER_USER=100
CHARACTER_RELAY_MAX_SCENARIOS_PER_USER=250
CHARACTER_RELAY_MAX_TEST_PACKS_PER_USER=100
CHARACTER_RELAY_MAX_RUNS_PER_USER=2000
CHARACTER_RELAY_MAX_MATRICES_PER_USER=100
CHARACTER_RELAY_MAX_MATRIX_TASKS_PER_DAY=1000
CHARACTER_RELAY_MAX_CONCURRENT_RUNS_PER_USER=3
CHARACTER_RELAY_MAX_MATRIX_CONCURRENCY_PER_USER=4
CHARACTER_RELAY_MAX_WORKSPACE_RECORDS_PER_USER=3000
```

The legacy `CHARACTER_RELAY_ADMIN_TOKEN`, Adaptive key, and Judge key settings remain read-only migration fallbacks. Production Admin APIs require an authenticated account with the `admin` role; the Portal does not use an Admin-token header.

## Backup-first migration

Stop writes or place the service in a maintenance window. Run:

```bash
python scripts/phase15_migrate.py \
  --database-url sqlite:////data/echo_masque.db \
  --backup-directory /data/backups
```

The command copies the existing SQLite database before creating missing Phase 15 tables. Re-running it is safe and preserves the same storage instance ID.

After creating the bootstrap Admin, legacy `local-user` data can be claimed through **Account & security → Admin control → Claim legacy local workspace**, or during migration:

```bash
python scripts/phase15_migrate.py \
  --database-url sqlite:////data/echo_masque.db \
  --claim-user-email admin@example.com
```

The claim is idempotent: a second attempt reports that no unclaimed data remains.

## Account model

- Passwords use Argon2 hashes.
- Browser authentication uses an opaque, revocable, expiring server-side Session.
- The browser receives an HttpOnly, SameSite cookie and does not store the Session token.
- Clients cannot select their workspace owner through headers or request payloads.
- `X-Echo-User` and `X-Echo-Admin` are rejected as Production identity boundaries.
- Public registration may be enabled explicitly; the default Production flow uses single-use invitation codes.
- Invitation codes are stored only as SHA-256 hashes and are returned once when created.

## Credential vault

Character provider keys and shared Adaptive/Judge keys are encrypted with Fernet before entering SQLite. API responses expose only status, source, and key version metadata.

To rotate keys:

1. Generate a new Fernet key.
2. Set `CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<new>,<old>`.
3. Redeploy.
4. Use **Rotate encrypted credentials** in the Admin account panel.
5. Run the live security smoke.
6. Remove the old key and redeploy only after acceptance passes.

Workspace exports exclude encrypted blobs, raw keys, Session tokens, password hashes, and invitation codes.

## Quotas and abuse controls

Login failures and authenticated request buckets persist in SQLite, so a restart does not clear temporary blocks. Server-side limits cover Characters, Scenarios, Test Packs, Runs, Matrices, workspace imports, daily Matrix tasks, and per-account concurrency.

A blocked request returns `429 Too Many Requests`; time-bound blocks include `Retry-After`.

## Account lifecycle

Users can:

- inspect and revoke Sessions in server-paginated pages of 20;
- export a secret-free account workspace archive;
- delete their account with email and confirmation phrase verification.

Account deletion removes owned workspace resources, encrypted credentials, Sessions, and rate-limit state. The user row is anonymized and disabled so historical Audit Event foreign-key references remain valid. The final interactive Admin cannot delete or demote itself.

Admin users can:

- create and revoke invitations;
- page through active accounts, search active accounts by name or email, and use the
  same bounded search when granting Discord Server access;
- promote and demote accounts while retaining at least one Admin;
- delete another account through the same workspace-removal, credential cleanup,
  Session revocation, and identity-anonymization lifecycle used by self-deletion;
- inspect append-only Audit Events;
- claim pre-authentication local workspace data;
- rotate encrypted credentials.

The Administration deletion route cannot delete the currently authenticated Admin.
That account must use the confirmed self-deletion flow, and the final active Admin
remains protected in both flows.

## Live release gate

Add repository secrets:

```text
ECHO_MASQUE_LIVE_ADMIN_EMAIL
ECHO_MASQUE_LIVE_ADMIN_PASSWORD
```

Then run **Phase 15 Live Security Smoke** from GitHub Actions. The workflow:

1. signs in as Admin;
2. creates two single-use invitations;
3. registers two temporary users;
4. verifies User B receives `404` for User A's private Character Card;
5. stores a temporary provider credential and confirms Vault status;
6. rotates the Vault and confirms the credential remains usable;
7. verifies account export contains no plaintext or encrypted credential material;
8. deletes both temporary accounts.

The JSON artifact is secret-free acceptance evidence. Run it after the Phase 15 deployment and after every encryption-key rotation or authentication migration.
