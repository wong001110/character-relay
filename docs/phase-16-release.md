# Phase 16 — Release, Templates, Sharing, and Migration

## Release scope

Phase 16 turns Echo Masque into a controlled evaluation-engineering workspace:

- AI-assisted Scenario and Test Pack Drafting
- explicit human review and approval
- human-controlled Calibration Datasets
- immutable Judge Evaluation Snapshots
- Rubric comparison and six-dimension coverage analytics
- reusable bilingual templates
- secret-free Evaluation Share Bundles
- server-enforced generation, evaluation, template, and sharing quotas

## Template authority boundary

Built-in templates never create formal Scenarios or formal Test Packs directly.

Instantiation produces:

1. Scenario Drafts
2. one Test Pack Draft referencing those Drafts
3. provenance and review notes

The normal Phase 16A approval state machine remains mandatory. A Test Pack Draft cannot be approved until all referenced Scenario Drafts have been approved.

## Evaluation Share Bundle

The Share Bundle schema is versioned as `schema_version: "1"`.

A bundle may include:

- formal Scenario contracts
- formal Test Pack structure
- language, severity, messages, expected behavior, and Judge recommendations

A bundle never includes:

- owner IDs
- account data
- Session tokens
- invitation codes
- API keys
- encrypted credential values
- Environment Secret values
- Character Runtime credentials
- Calibration labels or private Run transcripts

Importing a bundle creates reviewable Scenario and Test Pack Drafts only. It does not recreate formal resources automatically.

## Production quotas

Application settings use the `CHARACTER_RELAY_` environment prefix.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `CHARACTER_RELAY_MAX_AUTHORING_GENERATIONS_PER_DAY` | 50 | AI Authoring Runtime calls per account per day |
| `CHARACTER_RELAY_MAX_EVALUATION_CASES_PER_DAY` | 1000 | Judge Case predictions per account per day |
| `CHARACTER_RELAY_MAX_TEMPLATE_INSTANTIATIONS_PER_DAY` | 100 | Template and Share Bundle import operations per account per day |
| `CHARACTER_RELAY_MAX_SHARED_ASSETS_PER_BUNDLE` | 200 | Maximum expanded Scenario + Test Pack assets in one bundle |

Quota counters are stored in the existing persistent security bucket table. They survive application restarts and Railway redeployments through the managed PostgreSQL production database.

## Upgrade and migration

Phase 16 uses migration-safe table creation through the existing database initializer. Existing Phase 15 workspaces remain valid.

Before deployment:

1. Verify PostgreSQL backup/restore and pgvector availability.
2. Preserve the Credential Vault encryption keys.
3. Back up the account Workspace, Authoring, and Calibration archives before destructive infrastructure changes.

After deployment:

1. Confirm `/api/auth/config` reports authentication required.
2. Confirm `/api/templates` is available to an authenticated user.
3. Instantiate a template and verify formal Scenario/Test Pack listings remain unchanged until approval.
4. Export and re-import a Share Bundle and verify it returns Drafts only.
5. Inspect a prompt-model Character Runtime Prompt and test all four export formats.
6. Run a Rules Evaluation against an approved Calibration Dataset.
7. Open Coverage Lab and verify the six dimensions are reported.
8. Run the retained `Phase 16 Live Acceptance` GitHub Actions workflow.

## Retained Production acceptance

The workflow `.github/workflows/phase16-live-acceptance.yml` uses the existing Live Admin GitHub Secrets and creates one temporary invited user. It validates:

- template Draft boundaries
- formal Scenario approval
- secret-free Share Bundle export/import
- exact Runtime Prompt inspection
- TXT, Markdown, full JSON, and OpenAI messages exports
- Calibration Dataset approval
- Rules Evaluation Snapshot persistence
- Coverage reporting
- temporary-account cleanup

The evidence artifact is redacted and contains only resource IDs, counts, statuses, and export-format names.
