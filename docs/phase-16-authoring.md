# Phase 16 — Reviewable Authoring and Evaluation Engineering

Phase 16 extends Echo Masque from execution and comparison into controlled evaluation design. The central rule is that generated content never becomes executable ground truth without an explicit human approval action.

## Phase 16A status

Phase 16A establishes the review boundary and portable persistence layer for Scenario Drafts and Test Pack Drafts.

Implemented resources:

- owner-scoped Scenario Drafts;
- owner-scoped Test Pack Drafts and ordered items;
- manual or AI provenance metadata;
- review notes and monotonically increasing revisions;
- `draft`, `rejected`, and `approved` states;
- explicit approval into existing Phase 13 Scenarios and Test Packs;
- secret-free Authoring Archive export/import;
- Audit Events for authoring mutations and archive operations;
- account deletion and legacy `local-user` claim integration.

Phase 16A does not call an AI model. The Authoring Runtime, structured generation, heuristics, and Authoring Lab UI belong to Phase 16B.

## Review state machine

```text
create
  -> draft
      -> revise -> draft (revision + 1)
      -> reject -> rejected
          -> revise -> draft (revision + 1)
      -> approve -> approved + formal Scenario/Test Pack
```

Approved drafts are immutable provenance records. They cannot be revised, rejected, approved a second time, or deleted. The approved formal Scenario or Test Pack remains a normal Phase 13 resource and is the only object visible to existing Test Room, Test Pack launcher, and Matrix execution paths.

A draft therefore cannot be run accidentally:

- Scenario Drafts never appear in `/api/scenarios`;
- Test Pack Drafts never appear in `/api/test-packs`;
- existing Trial and Matrix contracts accept only formal resource IDs;
- approval is an authenticated owner-scoped mutation.

## Provenance

Every draft stores non-secret provenance:

```json
{
  "source": "manual | ai",
  "character_card_id": "optional owner-scoped source card",
  "source_model": "optional model identifier",
  "prompt_hash": "optional SHA-256 digest",
  "risk_tags": ["identity", "false memory"],
  "generated_at": "optional timestamp"
}
```

Raw prompts, Provider credentials, Session tokens, passwords, and encryption material are not provenance fields.

## Scenario Draft approval

Scenario Draft input uses the same validated fields as a formal Scenario, plus provenance and review notes. Approval creates a new formal Scenario with a new ID and stores that ID on the immutable Draft.

Relevant endpoints:

```text
GET    /api/authoring/scenario-drafts
POST   /api/authoring/scenario-drafts
GET    /api/authoring/scenario-drafts/{draft_id}
PUT    /api/authoring/scenario-drafts/{draft_id}
POST   /api/authoring/scenario-drafts/{draft_id}/reject
POST   /api/authoring/scenario-drafts/{draft_id}/approve
DELETE /api/authoring/scenario-drafts/{draft_id}
```

## Test Pack Draft approval

A Test Pack Draft item references either:

- an existing formal Scenario; or
- a Scenario Draft in the same owner workspace.

A Test Pack Draft cannot be approved until every referenced Scenario Draft is approved. At approval time each Draft reference resolves to its formal Scenario ID. Duplicate resolved Scenario IDs are rejected.

Relevant endpoints:

```text
GET    /api/authoring/test-pack-drafts
POST   /api/authoring/test-pack-drafts
GET    /api/authoring/test-pack-drafts/{draft_id}
PUT    /api/authoring/test-pack-drafts/{draft_id}
POST   /api/authoring/test-pack-drafts/{draft_id}/reject
POST   /api/authoring/test-pack-drafts/{draft_id}/approve
DELETE /api/authoring/test-pack-drafts/{draft_id}
```

## Authoring Archive

Phase 16A provides a separate secret-free archive so Draft provenance can be moved without expanding the stable Phase 13 Workspace Archive schema prematurely.

```text
GET  /api/authoring/archive
POST /api/authoring/archive/import
```

Import modes:

- `merge`: import missing Draft IDs and skip owner-matching duplicates;
- `replace`: remove the current account's Draft resources before restoring the archive.

Approved Drafts reference formal Phase 13 resources. When moving between databases, import the normal Workspace Archive first, then import the Authoring Archive. This ensures approved Scenario and Test Pack IDs already exist and belong to the importing account.

The Authoring Archive excludes:

- API keys and encrypted credential blobs;
- passwords and password hashes;
- Session tokens;
- invitation codes;
- raw model prompts not explicitly stored as normal Scenario content.

## Ownership and lifecycle

All Draft APIs derive ownership from the authenticated Session. Cross-user reads and mutations return `404` rather than confirming another account's resource exists.

Account deletion removes:

- Scenario Drafts;
- Test Pack Drafts;
- Test Pack Draft items.

The legacy workspace claim also moves future `local-user` authoring Drafts into the authenticated Admin account.

## Audit actions

Phase 16A adds append-only events for:

```text
authoring.scenario_draft_created
authoring.scenario_draft_revised
authoring.scenario_draft_rejected
authoring.scenario_draft_approved
authoring.scenario_draft_deleted
authoring.test_pack_draft_created
authoring.test_pack_draft_revised
authoring.test_pack_draft_rejected
authoring.test_pack_draft_approved
authoring.test_pack_draft_deleted
authoring.archive_exported
authoring.archive_imported
workspace.authoring_local_claimed
```

Audit metadata contains IDs, source type, revision numbers, import counts, and status metadata only.

## Next slice — Phase 16B

Phase 16B will add:

- an Admin-managed Authoring Runtime profile;
- encrypted Authoring Runtime credentials;
- Character Card and known-risk generation input;
- strict structured Scenario/Test Pack drafting with bounded correction;
- duplicate, risk, and coverage heuristics;
- English and Simplified Chinese generation;
- a bilingual Authoring Lab review interface.

Generated output will still enter Phase 16A as a Draft and will remain non-executable until approved.