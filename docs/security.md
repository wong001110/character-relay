# Security and Privacy Notes

Echo Masque is designed for test data and development environments. It is not a substitute for a full production red-team or compliance program.

## Credential model

- Model and external-target credentials are resolved from environment variables at runtime.
- Persisted target configuration contains only the environment-variable name.
- API responses, Trace, replay, comparisons, and reports pass through recursive redaction.
- Direct credential fields such as `api_key`, `authorization`, `access_token`, `password`, and cookies are replaced with `[REDACTED]`.
- Token usage fields such as `input_tokens` and `output_tokens` are retained because they are metrics, not credentials.

## External targets

- Only connect targets that the operator is authorized to test.
- Prefer a dedicated test environment and dedicated test credential.
- The adapter uses explicit timeouts and isolated session identifiers.
- Target errors are recorded as run failures and are not misclassified as behavioral verdicts.

## Data retention

SQLite stores target metadata, trial messages, target replies, evidence, and traces. Test data may contain personal or confidential content. Operators should use synthetic data where possible, control file access, and delete databases that are no longer required.

## Deployment

The included container runs as a non-root user. Production deployments should add TLS termination, authentication, authorization, rate limiting, database backups, and network restrictions before accepting untrusted users.
