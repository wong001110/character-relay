# Phase 16C — Human-approved Calibration Datasets

Phase 16C introduces versioned ground-truth datasets for evaluating Judge quality. Calibration labels and evidence are controlled by authenticated users, not generated or approved by AI.

## Dataset lifecycle

A Calibration Dataset moves through:

```text
draft -> approved -> archived
```

Only a Draft may be edited or deleted. Approval requires at least one Case. Approved and archived versions are immutable. Create **New version** to copy the frozen Cases into the next editable version while retaining the lineage and parent relationship.

## Calibration Cases

Each Case freezes:

- Scenario identity, name, category, and language;
- optional Character Card and completed Run references;
- one Tester message and Subject response;
- expected `PASS`, `FAIL`, or `REVIEW` verdict;
- failure type;
- exact grounded evidence excerpt;
- coverage dimensions;
- human review notes.

`FAIL` and `REVIEW` require a failure type and evidence. Evidence must be an exact contiguous substring of the frozen Subject response.

## Run import

A Case may be imported from a completed owner-scoped Run by supplying:

- Run ID;
- Scenario ID;
- one-based Turn index;
- human-selected expected verdict;
- optional grounded evidence and coverage dimensions.

The server loads the immutable Run Snapshot and persisted Turn. It does not rerun the Character or ask a model to reconstruct the answer.

## Archive portability

`GET /api/calibration/archive` produces a secret-free JSON archive. It contains no passwords, API keys, Session tokens, encrypted credentials, or Runtime configuration.

Import supports `merge` and `replace`. Same-owner restores preserve IDs. Cross-account sharing remaps Dataset, Lineage, Parent, and Case IDs so an imported asset cannot overwrite another user's resource.

## Account lifecycle

Calibration Dataset and Case rows are deleted during destructive account deletion. Historical `local-user` resources participate in the Admin ownership-claim flow.

## UI

Open **Calibration Lab** from the authenticated application shell to:

- create and select Dataset versions;
- author manual Cases;
- import completed Run Turns;
- approve, archive, or create a next version;
- inspect frozen Cases and evidence;
- download or restore a Calibration Archive.

The UI is available in English and Simplified Chinese.

## HTTP API

- `GET/POST /api/calibration/datasets`
- `GET/PUT/DELETE /api/calibration/datasets/{dataset_id}`
- `POST /api/calibration/datasets/{dataset_id}/approve`
- `POST /api/calibration/datasets/{dataset_id}/archive`
- `POST /api/calibration/datasets/{dataset_id}/new-version`
- `POST /api/calibration/datasets/{dataset_id}/cases`
- `POST /api/calibration/datasets/{dataset_id}/cases/import-run`
- `PUT/DELETE /api/calibration/cases/{case_id}`
- `GET /api/calibration/archive`
- `POST /api/calibration/archive/import`
