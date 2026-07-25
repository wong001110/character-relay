# Manual MVP Validation

These checks require human judgment or real external credentials. They do not block automated development completion.

## Character Shelf and Card Creator

- [ ] Confirm Stable Ann and Fragile Ann read as distinct collectible Character Cards.
- [ ] Create a user-owned card and confirm its target binding and profile notes are correct.
- [ ] Confirm the scrapbook treatment remains readable rather than decorative noise.
- [ ] Inspect the shelf at desktop, tablet, and narrow mobile widths.

## Live Test Room

- [ ] Run Stable Ann in Watch Mode and confirm left/right chat order is clear.
- [ ] Run Fragile Ann in Memory Room and confirm the fracture banner is obvious.
- [ ] Confirm Tester, Subject, Judge memo, and room-divider events are distinguishable.
- [ ] Confirm auto-scroll remains comfortable during Echo Hall.
- [ ] Compare Watch Mode with Fast Mode and confirm both have a useful purpose.
- [ ] Confirm Stop Session produces a clear cancelled state.

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
