# Phase 14 — Batch Experiment Matrix and Comparative Analytics

Phase 14 turns one-at-a-time Trials into controlled, reproducible batch experiments.

## Matrix definition

A Matrix combines:

- one or more Character Cards;
- optional immutable Prompt versions;
- optional Model overrides;
- optional Temperature overrides;
- one or more Test Packs;
- English and/or Simplified Chinese;
- Benchmark and/or Adaptive Tester;
- Rules, Semantic, and/or Hybrid Judge;
- a repeat count.

The server expands the Cartesian product and returns an exact task count before launch. The caller must confirm that same count. The server rejects stale confirmations and Matrices above the hard task cap.

## Queue model

Matrix definitions, tasks, attempts, retries, backoff metadata, and linked Run IDs are stored in SQLite. API keys are never stored in Matrix records.

Tasks move through `pending`, `running`, `completed`, `failed`, or `cancelled`. Matrices support pause, resume, cancel remaining work, and retry failed work. After an application restart, interrupted running tasks return to `pending` and their Matrix becomes `paused` for explicit operator review.

The MVP queue runs inside the application process with bounded concurrency. Phase 14 does not add a distributed worker fleet.

## Prompt versions

Prompt + Model Character Cards receive immutable versions when Provider, Base URL, Model, System Prompt, or Temperature changes. A version may be restored or marked as the production version. Old Run snapshots continue to reference the exact version used.

Raw credentials and credential environment-variable values are excluded from Prompt versions.

## Analytics

Completed Matrix Runs aggregate:

- mean, minimum, and maximum score;
- variance and standard deviation;
- pass, review, and failure rates;
- failure-type distribution;
- first-breakpoint frequency;
- input/output tokens;
- latency;
- provider errors and retries.

Breakdowns are available by Character, Prompt version, Model, Temperature, language, Tester, Judge, and Scenario.

## Regression

A completed Matrix may be marked as a baseline. Regression comparison requires compatible Test Packs, languages, Tester modes, and Judge modes. Compatible comparisons classify the candidate as improved, no meaningful change, or regression. Incompatible comparisons list the conflicting dimensions rather than producing a misleading verdict.

## Export

Matrix definitions, task metadata, and aggregate analytics are exportable as JSON, CSV, or Markdown. Exports must not include Subject, Adaptive Tester, Semantic Judge, or Admin credentials.

## UI

The Matrix Lab is separate from the Scenario/Test Pack Workspace and contains:

1. Builder — combinations, Prompt versions, preview, draft, and launch.
2. Queue — task progress and pause/resume/cancel/retry controls.
3. Analytics — metrics, variant breakdowns, regression, and exports.
4. Prompt Versions — history, restore, production marker, and diff.

The interface supports English and Simplified Chinese.

## Exclusions

Phase 14 does not include authentication, billing, public sharing, a Scenario marketplace, or distributed workers. Those boundaries remain in later roadmap phases.
