# Manual MVP Validation

These checks require human judgment or real external credentials. They do not block automated development completion.

## Character Shelf and Card Creator

- [ ] Confirm Stable Ann and Fragile Ann read as distinct collectible Character Cards.
- [ ] Create a Prompt + Model card and confirm provider, base URL, model, system prompt, and profile notes are correct.
- [ ] Create an Existing Target card and confirm its target binding is correct.
- [ ] Confirm the scrapbook treatment remains readable rather than decorative noise.
- [ ] Inspect the shelf and creator at desktop, tablet, and narrow mobile widths.

## Multilingual interface

- [ ] Open a fresh browser profile and confirm English is the default interface language.
- [ ] Switch to Simplified Chinese and confirm Character Shelf, Creator, Test Room, Credential, Adaptive Tester, and Report Modal controls update immediately.
- [ ] Refresh the browser and confirm the selected interface language is restored.
- [ ] Confirm the document language changes between `en` and `zh-CN`.
- [ ] Confirm character names, card fields, System Prompts, provider errors, and model responses remain in their original language.
- [ ] Confirm the EN / 简 controls remain readable on desktop and narrow mobile widths.

## Multilingual testing

- [ ] Keep the interface in English, select Simplified Chinese Test Language, and confirm the actual Tester messages are Chinese.
- [ ] Keep the interface in Simplified Chinese, select English Test Language, and confirm the actual Tester messages remain English.
- [ ] Run Stable Ann through all four English rooms and confirm the expected passing behaviour.
- [ ] Run Stable Ann through all four Simplified Chinese rooms and confirm the expected passing behaviour.
- [ ] Run Fragile Ann in Chinese Memory Room and confirm the Chinese forbidden phrase creates a breakpoint.
- [ ] Confirm Chinese Judge summaries, evidence messages, room contracts, and Lab Note headings are Chinese.
- [ ] Confirm JSON reports include `test_language` and preserve original Unicode model output.
- [ ] Run two English Benchmark sessions and confirm same-language comparison works.
- [ ] Run two Chinese Benchmark sessions and confirm same-language comparison works.
- [ ] Confirm an English Run cannot be used as the regression baseline for a Chinese Run.
- [ ] Configure a real Adaptive Tester in Chinese and confirm every generated follow-up stays in Simplified Chinese.
- [ ] Confirm imported Chinese transcripts use the Chinese rule catalog.

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

## Railway deployment

- [ ] Confirm `https://echo-masque-production.up.railway.app` shows the language switcher after deployment.
- [ ] Run the English Stable Benchmark on Railway.
- [ ] Run the Simplified Chinese Stable Benchmark on Railway.
- [ ] Redeploy and confirm prior multilingual runs survive through the `/data` volume.
- [ ] Confirm the automatic Railway Smoke workflow remains green after multilingual changes.

## End-to-end release

- [ ] Build the web client and serve it from FastAPI.
- [ ] Run the container with a persistent SQLite volume.
- [ ] Confirm a provider key entered through the UI is not present in the persistent volume.
- [ ] Compare two completed same-language Benchmark runs and confirm the regression verdict matches the evidence.
