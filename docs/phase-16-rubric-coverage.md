# Phase 16E — Rubric Comparison and Coverage Analytics

## Authority model

Phase 16E reads approved, immutable Calibration Dataset versions and immutable Judge Evaluation Snapshots. It does not change expected verdicts, evidence, Dataset Cases, or historical predictions.

Rubric comparison is accepted only when both Evaluation Snapshots reference the same Dataset ID and Dataset version. This prevents apparent improvements caused by evaluating different ground truth.

## Rubric comparison

The comparison report includes:

- Semantic accuracy delta
- Macro precision, recall, and F1 context
- false-positive and false-negative rate deltas
- six Semantic dimension average deltas
- per-Case prediction changes
- an overall improved, regressed, mixed, or unchanged classification

Provider errors and missing Semantic predictions are excluded from eligible metric counts rather than converted into verdicts.

## Coverage model

Coverage is measured across six explicit dimensions:

1. identity
2. memory
3. instruction resistance
4. capability honesty
5. persona
6. language

A dimension is:

- `missing` with zero approved Cases
- `weak` with one or two approved Cases
- `covered` with at least three approved Cases

When an Evaluation Snapshot is selected, the report also calculates the available Semantic average score for every dimension.

## AI Draft boundary

Coverage gaps can be sent to the existing Phase 16B Authoring Runtime as risk tags. The model creates Scenario and optional Test Pack Drafts only. The normal Phase 16A review and explicit approval boundary remains in force.

Coverage analysis never creates formal Scenarios, Test Packs, Calibration labels, or approvals.

## API

- `GET /api/analytics/datasets/{dataset_id}/coverage`
- `GET /api/analytics/datasets/{dataset_id}/coverage?evaluation_id=...`
- `POST /api/analytics/rubrics/compare`

All endpoints derive ownership from the authenticated Session and return `404` for resources owned by another user.
