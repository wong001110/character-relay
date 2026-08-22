# Security and privacy

Status: **current security boundary**

Character Relay is an authenticated multi-user service, but it is not a substitute for an independent security review, threat model, backup program, or compliance assessment. Use synthetic/test content where possible and limited, revocable provider credentials.

## Identity and authorization

- Passwords use Argon2 hashes.
- Browser authentication uses opaque, revocable server-side Sessions in HttpOnly, SameSite cookies.
- API clients may use the supported Bearer-token flow.
- Production ownership is derived from the authenticated Session, not caller-selected `X-Echo-User`/`X-Echo-Admin` headers.
- Admin APIs require an authenticated account with the `admin` role; Bootstrap Admin-only trace surfaces have an additional role/identity boundary.
- Public registration is disabled by default; invitations are single use and stored as hashes.
- Public Demo mutation denial is enforced server-side.

Legacy header/token compatibility may exist only in non-production test/development modes. It must not be used as a production identity boundary or reintroduced into the Portal.

## Credentials

- User/provider and shared runtime credentials are stored through the encrypted Credential Vault.
- Vault encryption uses configured Fernet keys and supports key rotation.
- Some runtime settings support an explicit environment fallback; values remain server-side.
- API responses expose readiness/source/key metadata, never raw or encrypted credential values.
- Workspace/account/authoring/share exports exclude keys, encrypted blobs, password hashes, Sessions, invitation codes, and authorization headers.
- Logs, Runtime Trace, Provider Trace, reports, snapshots, replay, and diagnostics must remain recursively redacted.

Token-usage fields such as input/output token counts are metrics, not credentials, and may be retained.

## Scope and derived data

- Owner, Discord Server, channel/thread, deployment, Character, and relationship scope must not widen by inference.
- Derived Wiki/Graph/summary/index data may stay at the source scope or become narrower, never automatically wider.
- Raw messages, media references, completed Tool results, and external results are provenance evidence; derived state cannot silently replace or rewrite them.
- Planner-only media information is not Character-visible perception.

## External targets and tools

- Connect only systems the operator is authorized to test or operate.
- Prefer dedicated test environments and spending-limited credentials.
- External target configurations store an environment-variable name, not its value.
- Runtime validates tool proposals, scope, expiry, and side effects; model output is not authorization.
- Target/tool/provider failures are operational failures and must not be misclassified as behavioral evidence.

## Data retention and storage

SQLite stores account/product state, messages/evidence, traces, and evaluation records. Operators must control access, retention, backups, and deletion for any personal or confidential content.

The supported Railway topology is one replica with a persistent Volume mounted at `/data`. Confirm persistence using `storage_instance_id` and a cross-redeploy Probe; a correct-looking path alone is not proof of durability.

## Production checklist

- terminate TLS at the hosting platform;
- set `CHARACTER_RELAY_ENVIRONMENT=production` and secure cookie/auth settings;
- keep public registration and legacy local identity disabled unless explicitly required;
- keep credentials and encryption keys outside Git;
- retain at least one old Fernet key until stored credentials have been rotated and verified;
- use one replica while SQLite remains the database;
- back up and test restore procedures;
- run live account isolation, credential rotation, redaction, Demo read-only, and deployment smoke checks after security/runtime changes.

See `docs/phase-15-security.md`, `docs/railway-deployment.md`, and `docs/manual-validation.md`.
