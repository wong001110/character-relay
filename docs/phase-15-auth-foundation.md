# Phase 15A — Authentication and Credential Vault Foundation

Phase 15 replaces caller-selected workspace identity with server-enforced authentication. This first delivery slice establishes the backend security boundary and migrates the Character Library before the remaining workspace routes are converted.

## Implemented in 15A

- persistent users with `user` and `admin` roles;
- Argon2 password hashing;
- opaque, random, revocable server-side sessions;
- HttpOnly `SameSite=Lax` browser cookies and Bearer-token API access;
- session listing and revocation;
- development/test-only `X-Echo-User` compatibility for the existing deterministic suite;
- production rejection of anonymous Character Library access;
- server-derived Character Card ownership;
- owner-scoped custom Target visibility, while internal demo Targets remain public for smoke tests;
- encrypted Subject provider credentials stored in SQLite;
- versioned encryption-key metadata and `MultiFernet` rotation support;
- append-only audit records for account, session, and credential mutations;
- persistence models reserved for invitations and later account lifecycle work.

## Production environment

Phase 15A introduces the following settings:

```text
ECHO_MASQUE_CREDENTIAL_ENCRYPTION_KEYS=<primary-fernet-key>[,<older-fernet-key>...]
ECHO_MASQUE_AUTH_COOKIE_NAME=echo_masque_session
ECHO_MASQUE_AUTH_SESSION_TTL_SECONDS=2592000
ECHO_MASQUE_AUTH_COOKIE_SECURE=true
ECHO_MASQUE_PUBLIC_REGISTRATION_ENABLED=false
ECHO_MASQUE_LEGACY_LOCAL_USER_ENABLED=false
```

Generate a Fernet key outside the application and store it as a Railway secret. During rotation, place the new key first and retain the previous key after it until stored credentials have been rotated. Never commit a key or place one in a workspace export.

Production must keep public registration disabled until the invitation flow is delivered. The first production administrator will be created through the Phase 15 migration/bootstrap command rather than through public self-registration.

## Compatibility boundary

Existing tests and local development may continue using `X-Echo-User` only when all of the following are true:

1. the environment is not `production`;
2. `ECHO_MASQUE_LEGACY_LOCAL_USER_ENABLED=true`;
3. no valid Session cookie or Bearer token is present.

The header is ignored as an ownership authority once a real session is supplied, and it is never accepted in production.

## Remaining Phase 15 work

- migrate Scenarios, Packs, Runs, Reports, Matrices, exports, imports, and probes to the authenticated user dependency;
- replace `X-Echo-Admin` with authenticated role-based authorization;
- persist encrypted Adaptive Tester and Semantic Judge credentials;
- implement invitation issuance and acceptance;
- add login throttling, per-user quotas, and abuse controls;
- add session/account UI and bilingual copy;
- add account deletion, user-scoped export, and `local-user` workspace claiming;
- run live two-account isolation and credential-rotation acceptance.
