# Manual MVP Validation

These checks require human judgment or real external credentials. They do not block automated development completion.

## Observation interface

- [ ] Run Stable Ann with all suites and confirm the interface clearly communicates an intact result.
- [ ] Run Fragile Ann with all suites and confirm the first breakpoint is visually obvious.
- [ ] Inspect the interface at desktop, tablet, and narrow mobile widths.
- [ ] Confirm long-session transcript scrolling remains understandable.
- [ ] Confirm loading, empty, failed, and completed states are distinguishable.

## Real model provider

- [ ] Configure an OpenAI-compatible test endpoint and credential environment variable.
- [ ] Run one identity test and confirm latency and token metadata are captured.
- [ ] Confirm provider errors do not expose the credential in UI, logs, database, or reports.

## External chatbot

- [ ] Connect a separately hosted chatbot through the documented HTTP contract.
- [ ] Confirm a new isolated session is created for every scenario.
- [ ] Confirm optional Trace data appears and sensitive headers are redacted.
- [ ] Confirm reset, timeout, authentication rejection, and malformed response diagnostics.

## End-to-end release

- [ ] Build the web client and serve it from FastAPI.
- [ ] Run the container with a persistent SQLite volume.
- [ ] Export Markdown and JSON reports and inspect their readability.
- [ ] Compare two completed runs and confirm the regression verdict matches the evidence.
