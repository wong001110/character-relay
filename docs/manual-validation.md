# Manual MVP Validation

These checks require human judgment or real external credentials. They do not block automated development completion.

## Character Shelf and Card Creator

- [ ] Confirm Stable Ann and Fragile Ann read as distinct collectible Character Cards.
- [ ] Create a Prompt + Model card and confirm provider, base URL, model, system prompt, and profile notes are correct.
- [ ] Create an Existing Target card and confirm its target binding is correct.
- [ ] Confirm the scrapbook treatment remains readable rather than decorative noise.
- [ ] Inspect the shelf and creator at desktop, tablet, and narrow mobile widths.

## Live Test Room

- [ ] Run Stable Ann in Watch Mode and confirm left/right chat order is clear.
- [ ] Confirm room opening, Tester message, typing, Subject response, Judge memo, breakpoint, and room transition have enough time to be read.
- [ ] Run Fragile Ann in Memory Room and confirm the fracture banner is obvious.
- [ ] Confirm auto-scroll remains comfortable during Echo Hall.
- [ ] Compare Watch Mode with Fast Mode and confirm both have a useful purpose.
- [ ] Confirm Stop Session produces a clear cancelled state.

## Live polling

- [ ] Open browser developer tools and confirm one `/snapshot` request replaces separate run and event requests.
- [ ] Confirm Watch Mode requests a snapshot approximately every 1.2 seconds while active.
- [ ] Confirm Fast Mode requests a snapshot approximately every 450 milliseconds while active.
- [ ] Confirm polling stops immediately after completed, failed, or cancelled status is returned.
- [ ] Confirm event ordering and the final result remain correct when several events arrive in one snapshot.

## Adaptive Tester

- [ ] Select Benchmark Tester and confirm the fixed scripts remain reproducible across runs.
- [ ] Configure Adaptive Tester with a separate provider, model, prompt, maximum turns, and API key.
- [ ] Confirm `Adaptive Tester planning` appears while the second model is generating.
- [ ] Confirm the generated follow-up responds to the Subject's previous answer.
- [ ] Confirm a clear forbidden-behavior response stops additional Adaptive Tester turns.
- [ ] Confirm Adaptive runs are not shown as deterministic regression comparisons.
- [ ] Inspect SQLite, events, reports, and logs and confirm the Adaptive Tester API key is absent.

## Reports

- [ ] Open the Lab Note modal and confirm long reports remain readable and scrollable.
- [ ] Open the JSON modal and confirm indentation, copy, and download behaviour.
- [ ] Confirm neither report exposes an API key or sensitive header.

## Real model provider

- [ ] Create a DeepSeek, OpenAI, OpenRouter, or custom compatible Prompt + Model Character Card.
- [ ] Run one identity test and confirm the configured model answers in the live room.
- [ ] Confirm latency and token metadata are captured.
- [ ] Restart the backend and confirm the Test Room requests the API key again.
- [ ] Reconfigure the key and rerun successfully.
- [ ] Confirm missing, rejected, and timed-out credentials produce clear errors without exposing the raw key.

## One-command launcher

- [ ] From a clean checkout with Python 3.12+ and Node.js 22+, run `python run.py`.
- [ ] Confirm `.venv` is created and Python and web dependencies are installed.
- [ ] Run `python run.py` again and confirm unchanged dependency installation is skipped.
- [ ] Confirm FastAPI starts on port 8000 and Vite starts on port 5173.
- [ ] Press Ctrl+C once and confirm both child processes stop.
- [ ] Repeat the launcher check on Windows and macOS or Linux.

## External chatbot

- [ ] Connect a separately hosted chatbot through the documented HTTP contract.
- [ ] Confirm a new isolated session is created for every scenario.
- [ ] Confirm optional Trace data appears and sensitive headers are redacted.
- [ ] Confirm reset, timeout, authentication rejection, and malformed response diagnostics.

## End-to-end release

- [ ] Build the web client and serve it from FastAPI.
- [ ] Run the container with a persistent SQLite volume.
- [ ] Confirm a provider key entered through the UI is not present in the persistent volume.
- [ ] Compare two completed Benchmark runs and confirm the regression verdict matches the evidence.
