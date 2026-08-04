# Provider request and response tracing

Character Relay writes correlated structured JSON events for every OpenAI-compatible provider call, including DeepSeek.

The logs appear in the Character Relay Web/API service logs, not the Discord Connector service logs.

## Events

```text
provider.request
provider.retry
provider.response
provider.error
```

Every event contains the same `trace_id`, plus the endpoint, model, status, latency, token usage, and retry/error details when available. Authorization headers and API keys are never logged.

## Trace modes

```text
ECHO_MASQUE_PROVIDER_TRACE_MODE=off
ECHO_MASQUE_PROVIDER_TRACE_MODE=metadata
ECHO_MASQUE_PROVIDER_TRACE_MODE=summary
ECHO_MASQUE_PROVIDER_TRACE_MODE=content
```

- `off`: no provider trace events.
- `metadata`: model, endpoint, roles, character counts, latency, status, and token usage only.
- `summary` (default): metadata plus the latest non-system request message and the response text.
- `content`: metadata plus the full request message sequence and response text, bounded by the configured character limit.

Set the maximum logged text budget with:

```text
ECHO_MASQUE_PROVIDER_TRACE_MAX_CHARS=4000
```

The accepted range is 256 to 20000 characters. Truncated text includes an omitted-character marker.

`content` mode may expose system prompts and private conversation text to anyone who can read the deployment logs. Use it only during controlled debugging, then return to `summary`, `metadata`, or `off`.
