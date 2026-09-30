# Room Director R1 offline verification — 2026-10-01

This is a verification receipt, not another progress ledger. Current status and next work live in
[PROJECT_STATE.md](../../PROJECT_STATE.md). All review here is **self-review**.

## Source and corpus identities

Baseline: `2812d79b314b25aa31fe0632dcbdd7da205b0bf0` (PR #207). Direction was committed first in
`94be0361ef5c4c77bdbf180146beb6f49a5dc6d2`; R1 source in
`f3933d01f43cfe40d42369db0e927d0151f1480f`. The follow-up fixture/docs/dependency commit does not
change these three executable modules. The final PR/CI identifies its own exact head.

| Artifact | SHA-256 |
| --- | --- |
| `room_routing.py` | `7dd20a552ec62ee3308b160bcb399a1000707b432bbd1cd098a95d8a83ffe209` |
| `room_director.py` | `cd6f9cbf953feb36993974f735b34b59e10f1bc2edf134ae193506440167895f` |
| `room_routing_replay.py` | `fd4a57acb8e3aa9edb376f108e914a6bfe5568cd6359d5e4ab57c2d7d4a5c1c0` |
| CLI combined module identity | `e970c33a07c354efb27d00139bd8be647b91637ab02c755d4ecb94aacffd5487` |
| Decompressed corpus | `7711a706d68d5e3e0f596802c200adef4b95aba8c106dbc4ebb19412f23fcf48` |

The source acquisition artifact reconstructed the exact Git tree, not a guessed file subset.
GitHub artifact run `36769995334` exported source/test wheels; run `36774824091` reproduced and
hash-checked the synthetic fixture. Neither run was a model benchmark or full application CI.
The acquisition workflow is removed before the review checkpoint; no permanent coding-agent or
source-export workflow remains. No credentials/private transcripts were exported.

## Local checks actually run

Python 3.13.5, Pydantic 2.13.5, SQLAlchemy 2.0.50; normal deterministic test encoder defaults.
Commands use `PYTHONPATH=src` to select the working source, not the initial installed wheel.

| Command / scope | Result |
| --- | --- |
| `pytest tests/test_room_routing.py tests/test_room_routing_replay.py tests/test_room_routing_legacy_replay.py tests/test_participation_planner_v3.py tests/test_smart_participation_v3_route.py tests/test_provider_trace_metadata_default.py --tb=short` | 346 passed |
| `ruff check .` | Passed across repository |
| `mypy src` | Passed, 406 source files |
| Corpus regeneration, plain/gzip identity and CLI rules/score | Passed in focused tests |
| Actual native Planner adapter with explicit fake semantics | Passed; Planner stage only, not live encoder/full pipeline |

The 346 include the 240 parameterized corpus checks; do not add those counts together. Generated
labels are not used as model predictions. Rules-only smoke: 240 cases / 256 new messages, zero
model calls, 0/48 missed required direct responses, 56/80 expected-speaking speaker matches.
Its expected ambient omissions are deliberate; these fixture statistics are not population quality
or evidence that a Director improves them. No real Director output or live cost/latency was measured.

## Mutation scope and survivor disposition

Executed with fresh profiling after assertion changes:

```bash
mutmut run '*room_routing*route_rules*' '*room_routing*visible_messages*' '*room_routing*eligible_roles*' '*room_director*validate_decision*' '*room_director*_unique_object*' --max-children 2
```

**240 executed: 222 killed, 18 survived; zero timeouts/tool errors in that set.** The generator
listed more mutants outside this bounded selection; they are untested, not killed or waived.
Scope covers exact-scope filtering, eligibility, direct routing/capacity/requester metadata,
decision membership/bounds and duplicate-key rejection. It does not claim mutation coverage of
the full provider, replay metrics, Pydantic validators, production permissions or transport.

| Surviving mutation keys (function-local suffixes) | Self-reviewed disposition |
| --- | --- |
| `route_rules`: 53, 55, 56 | Initial sentinel value changes, overwritten before an observable result |
| `route_rules`: 103 | Equivalent under the validated character-kind/deployment-ID invariant; invalid bypassed model objects are outside the normalized contract |
| `_unique_object`: 3-6 | Duplicate-key error-message text only; same rejection and invalid-result semantics |
| `validate_decision`: 3-6, 16-19, 22-23 | Rejection-message text only; same rejected inputs, no acceptance or semantic NONE change |

No survivor is presented as an independent security signoff. Earlier runs exposed real missing
assertions for human requester/explicit targets, ambient capacity 0 vs 1, 4096 vs 4097 output size
and duplicate keys whose final values form valid NONE. Tests were strengthened and the scope
re-run; no production checks were weakened. Other self-review fixes separated action actor from
selected-message author and removed scenario names from model-visible message IDs.

## Dependency compatibility boundary

The old `sqlalchemy>=2.0,<3.0` range selected 2.1.1. On pristine baseline (403 modules) and this
source (406), mypy reproduced the same 18 errors in unchanged `media_singleflight.py` and
`persistence/provider_trace_repository.py`. SQLAlchemy's
[2.1 migration notes](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html) document changed
PEP 646 Select/Result typing. This checkpoint constrains the existing dependency to
`sqlalchemy>=2.0,<2.1`; it does not mix a database-library migration into routing work. With 2.0.50,
whole-source mypy passes. Local offline verification used host-installed 2.0.50 package bytes;
normal CI independently installs published compatible packages. Full dependency/security audit
and a SQLAlchemy 2.1 migration are not claimed.

## Reuse and safety boundaries

The spike reuses installed Pydantic, pytest/mutmut and the actual legacy Planner test seam; no
AutoGen/Supervisor runtime, provider pool, service or new runtime package is added. The accepted
[reference decisions](../plans/discord-group-chat-core.md#reuse--reference-decisions) borrow
public-role selection, Reply-context and selected-card patterns, while rejecting forced speakers.
Free Token Pool integration still needs a bounded evaluated adapter, not blind reuse of permissive
JSON salvage or missing-usage-to-zero behavior.

No existing production graph/route/Connector imports the new routing path. Model output is only
a proposal; this offline schema is not a public authorization boundary. Runtime authentication,
permissions before prompts/effects, current source revisions and safe receipts still require R2/R3
integration. No ordinary-engine retirement, card migration, data purge or ambient activation occurred.

## Explicitly not verified here

Real Free Token Pool model quality/failover/latency/cost, human-reviewed labels, full old-pipeline
comparison, live Discord, production source/permission/delivery wiring, bot-to-bot end-to-end,
remote embedding behavior, card/reset rehearsal, Portal browser journeys and independent review.
The local focused checks are not full Python/Connector/Portal/PostgreSQL/Docker CI. Exact-head
remote CI results are separate receipts on the PR. Unavailable evidence remains unverified.
