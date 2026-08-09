# Provider request and response tracing

Character Relay persists correlated provider traces for OpenAI-compatible model calls, including DeepSeek. Provider request and response content is not written to Railway process logs.

The viewer is available inside the Portal only to the configured Bootstrap Admin account, which acts as the product's Super Admin. Regular Admin and User sessions receive `403 Forbidden` from the trace API.

## Portal access

```text
Sign in as the Bootstrap Admin
→ Provider Trace
```

The Portal supports status and model filters, manual or five-second refresh, request/response JSON inspection, copying JSON, and clearing retained traces.

Every trace uses one `trace_id` and may include:

```text
provider.request
provider.retry
provider.response
provider.error
```

Authorization headers and API keys are never persisted.

## Trace modes

```text
CHARACTER_RELAY_PROVIDER_TRACE_MODE=off
CHARACTER_RELAY_PROVIDER_TRACE_MODE=metadata
CHARACTER_RELAY_PROVIDER_TRACE_MODE=summary
CHARACTER_RELAY_PROVIDER_TRACE_MODE=content
```

- `off`: do not persist provider traces.
- `metadata`: model, endpoint, roles, character counts, latency, status, and token usage only.
- `summary` (default): metadata plus the latest non-system request message and response text.
- `content`: metadata plus the full request message sequence and response text, bounded by the configured character limit.

Set the per-event text budget with:

```text
CHARACTER_RELAY_PROVIDER_TRACE_MAX_CHARS=4000
```

The accepted range is 256 to 20000 characters. Truncated text contains an omitted-character marker.

`content` mode stores bounded System Prompt and private conversation content in the Character Relay database. It remains protected by the Super Admin API boundary, but should still be enabled only when that level of inspection is necessary.

## Retention

```text
CHARACTER_RELAY_PROVIDER_TRACE_RETENTION_DAYS=7
CHARACTER_RELAY_PROVIDER_TRACE_MAX_RECORDS=2000
```

Retention is bounded to 1–90 days and 100–10000 records. Oldest traces are pruned automatically when new requests are recorded. The Super Admin may also clear all traces from the Portal.
