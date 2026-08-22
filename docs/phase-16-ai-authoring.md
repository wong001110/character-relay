# Phase 16B — AI-assisted Scenario and Test Pack Drafting

Phase 16B adds an Admin-managed Authoring Runtime and a bilingual Authoring Lab. It does not allow a model to create executable ground truth.

## Authority boundary

The Authoring model may only create:

- Scenario Drafts;
- Test Pack Drafts;
- non-secret provenance and coverage warnings.

A generated Draft remains outside the normal Scenario, Test Pack, Trial, and Matrix execution paths. A user must inspect and explicitly approve it. Approval uses the Phase 16A state machine and creates a normal Phase 13 Scenario or Test Pack.

The model cannot create calibration labels, expected verdicts for completed responses, production baselines, or Judge-quality claims.

## Authoring Runtime

An Admin configures the Runtime from **Authoring Lab → Authoring Runtime**:

- enabled status;
- Provider;
- Base URL;
- Model;
- System Prompt;
- Temperature;
- maximum Scenario count per request;
- Provider API Key.

The API Key enters the Phase 15 encrypted Credential Vault under the shared system Runtime owner. The browser never persists or receives the raw key. `CHARACTER_RELAY_AUTHORING_API_KEY` is supported only as an optional read-only environment fallback.

## Structured generation

A generation request contains:

- one user-owned Character Card;
- English or Simplified Chinese output language;
- requested risk tags;
- known observed failures;
- optional author instructions;
- a bounded Scenario count;
- whether to also create a Test Pack Draft.

The server builds the Character and risk context, requests one strict JSON object, and validates it with Pydantic. A malformed response receives at most one formatting-repair request at temperature `0`. The repaired response must pass the same schema.

## Validation and heuristics

Before persistence, the server:

- verifies Character ownership;
- restricts categories, severities, modes, lengths, and counts;
- normalizes repeated messages and phrases;
- fingerprints the category, language, and first Tester message;
- rejects duplicates against formal Scenarios and existing Drafts;
- reports requested risk categories that have no retained Scenario.

Heuristics are warnings and duplicate guards, not evidence that the generated test is correct.

## Provenance

Every generated Draft records:

- `source=ai`;
- source Character Card ID;
- Provider-reported Model;
- SHA-256 hash of the complete generation context;
- requested risk tags;
- generation timestamp.

Prompt text and Provider credentials are not stored in the Draft or exposed through exports.

## HTTP API

Runtime status:

- `GET /api/authoring/runtime/status`

Admin Runtime management:

- `GET /api/admin/authoring-runtime`
- `PUT /api/admin/authoring-runtime`
- `PUT /api/admin/authoring-runtime/credential`
- `DELETE /api/admin/authoring-runtime/credential`

Draft generation:

- `POST /api/authoring/generate`

Draft review, revision, rejection, approval, deletion, and archive endpoints remain those introduced by Phase 16A.

## Production checks

Phase 16B must preserve:

- Phase 15 authenticated ownership;
- encrypted Credential Vault behavior;
- secret-free workspace and Authoring archives;
- Phase 15 live two-account isolation and Vault-rotation acceptance;
- Python 3.12 and 3.13 Ruff, strict mypy, and pytest;
- TypeScript, Vitest, Production build;
- Docker persistent-volume smoke;
- Railway smoke.
