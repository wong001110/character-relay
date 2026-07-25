# Custom HTTP Target Contract

Echo Masque can test a complete external chatbot without receiving its system prompt, model name, retrieval data, or internal source code.

## Message request

The default contract sends:

```json
{
  "session_id": "isolated-test-session",
  "message": "Trial message"
}
```

The field names are configurable. The default response is:

```json
{
  "response": "Target reply",
  "trace": {
    "tool_calls": [],
    "retrieved_memories": []
  }
}
```

`response_text_path` and `trace_path` accept dot-separated paths for nested payloads. Trace support is optional.

## Reset request

When `reset_url` is configured, Echo Masque posts a new `session_id` before every scenario. A successful reset may return an empty body.

## Authentication

A target configuration stores only an environment-variable name such as `ECHO_MASQUE_EXTERNAL_API_KEY`. Echo Masque resolves the value at runtime and sends it through the configured header and scheme. Credential values are never serialized in target configuration, traces, replay, or reports.

## Error behavior

Authentication rejection, timeout, unreachable targets, non-JSON responses, missing response paths, and non-string replies become explicit failed-run errors rather than behavior verdicts.
