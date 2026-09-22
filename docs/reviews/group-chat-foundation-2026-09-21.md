# Group-chat foundation verification

Evidence receipt, not a second execution tracker. Current status is in PROJECT_STATE.md.
Baseline: `efb66eda828726cfda9cda6e3b952e0ad32153fd` (PR #207 takeover from PR #206).
The implementation revision is the commit containing this receipt; verify the PR's exact-head CI.

## Scope and evidence level

Production-call-site changes: Connector ContextBuffer and mention alias generation, participation
selection persistence failure handling, and provider trace emission/classification/persistence.
No source relocation, schema migration, live environment mutation, extra model call or deployment.
This covers only parts of D03/D09/D10 and A04/A07/A19/A20. It does not complete those entire cases
or the P1-P6 programme. No independent reviewer or live naturalness/cost evidence is claimed.

Source was obtained via a short-lived read-only CI artifact because local Git DNS was unavailable.
The extracted source tar SHA256 was
`4cf8587c8e307c7bc027cc4e9b78432aba7262b66757564e719076de44bc8992`.
Its local Git tree matched remote `11a048a950cb0bc9b2f10a2b08c1552b416fbe00` exactly.
The temporary snapshot workflow is deleted in this slice; no credential/data artifact was needed.

## Executed checks

Python 3.13.5, local existing packages, source via `PYTHONPATH=src`:

```bash
python -m pytest \
  tests/test_provider_trace_metadata_default.py \
  tests/test_provider_trace.py \
  tests/test_provider_trace_tool_error_status.py \
  tests/test_trace_redaction_review.py \
  tests/test_provider_trace_media_attention.py \
  tests/test_provider_trace_tool_schema_budget.py \
  tests/test_media_provider_trace_observability.py \
  tests/test_smart_output.py \
  tests/test_interaction_grounding.py \
  tests/test_openai_compatible_provider.py \
  tests/test_platform_video_trace.py --tb=short
```

Result: **50 passed**. Default-mode omission, unknown usage, failed-tool diagnostics, category
promotion when a response calls a tool, diagnostic failure isolation, opt-in redaction and existing
provider retry behavior are checked. Before the change, six of seven initial metadata regressions
failed; explicit raw-content tests were made opt-in, not deleted or stripped of assertions.

Local Node 22.16 / TypeScript 5.8.3:

```bash
cd connectors/discord
tsc --noEmit --strict --noUncheckedIndexedAccess --exactOptionalPropertyTypes \
  --module NodeNext --target ES2023 --skipLibCheck \
  src/contextBuffer.ts src/smartOutput.ts
```

Result: passed. A temporary external node:test harness exercised the transpiled actual modules:
**12 passed**, covering original order/capacity, input/output/nested mutation isolation, stable
in-flight snapshots, room separation/clear, human priority despite role crowding, stable same-name
identities, known-role priority, rejection of display-name identification and ambiguous Card mapping,
and preserved explicit mention allowlists. The committed Vitest files cover the relevant regressions;
full supported-version Connector verification remains CI evidence, not this local harness.

Eight deliberately selected mutation probes (outside the repository) were each rejected by real
assertion failures: producer copy removed, consumer copy removed, duplicate moved to end, roles
reordered before people, raw trace restored by default, metadata error detail restored, failed-tool
count ignored, and safe character category ignored. This is not an exhaustive mutation score.

`git diff --check` passed. Upload tree hashes were compared to the staged local tree while assembling
the single source batch, ensuring uploaded content matches what the local checks exercised.

## Verification not claimed

Local route test collection cannot import `langgraph`; local Ruff/mypy/Vitest dependencies are
unavailable and package-network resolution fails. API integration, full strict typing/lint, the
complete Node suite, Docker/PostgreSQL and cross-project tests must be read from exact-head CI.
No stubs were inserted to manufacture route-test passes. No live Discord/provider credentials,
security attack on external systems, model-quality evaluation or production deployment was used.

## Residual constraints

Per-message Reply metadata and actual source/recipient pinning are still pending. No partial-send
fix or draft-refresh implementation is implied by immutable local snapshots. Metadata mode does
not remove prior prose or override an operator's explicit summary/content setting. Room-scoped
expiring raw captures and view/export auditing remain later work. Categories are diagnostics,
not authorization or evidence that a generated answer is correct.
