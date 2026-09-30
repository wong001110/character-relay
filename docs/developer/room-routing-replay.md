# Room-routing replay (P1 implementation)

This is offline evaluation infrastructure, **not a production routing switch**. The active
requirements are in [the group-chat plan](../plans/discord-group-chat-core.md); progress belongs
in [PROJECT_STATE.md](../../PROJECT_STATE.md).

## Reproduce the mechanical checks

Use the project's Python environment (`python -m pip install -e '.[dev]'`).

```sh
python -m pytest tests/test_room_routing.py tests/test_room_replay.py
PYTHONPATH=src python scripts/room_replay_seed.py > /tmp/room-seed.jsonl
python -m echo_masque.room_replay rules /tmp/room-seed.jsonl /tmp/room-rules.jsonl \
  --source-commit "$(git rev-parse HEAD)" --run-id rules-local
python -m echo_masque.room_replay compare /tmp/room-seed.jsonl /tmp/room-rules.jsonl
```

The seed generator supplies **24 synthetic, unreviewed calibration cases in eight template
families**, across English, Chinese and mixed text. It supplies no heldout cases. It is not the
200-500-point benchmark, not 24 independent conversations and not human-quality evidence.
Rules-only intentionally declines ambiguous requests, including the seeded useful math contribution.
Do not call its accuracy a product-quality result or derive Director superiority from these labels.

## Contracts and adapters

`room_routing.py` supplies strict immutable input/proposal/result models, deterministic explicit
routing, bounded public Director prompts and a qualified-free-provider async seam. Existing
Pydantic and the standard library are reused; no supervisor framework or dependency is added.

The caller must supply **verified** connector identities, effective eligibility, scope, per-role
visibility and a chronological bounded room snapshot. A field saying `eligible` or `visible_to`
is not itself evidence of permission. Filter before prompt construction and revalidate source,
grants and publication in the actual runtime. The module performs no tool/effect execution.

`route_direct()` returning Python `None` means routing remains ambiguous. It is not successful
model silence. `route_rules_only()` deliberately disables ambient participation. An explicit
unavailable role or source returns blocked/deferred work, not an unrelated replacement speaker.
Multiple explicit requests retain capacity-deferred entries that production must queue fairly.

`route_with_director()` bypasses models for direct work. It accepts only configured qualified free
identities, deduplicates providers, bounds total deadline/attempts, rejects malformed/extra/duplicate
JSON keys and unknown/invisible targets, and records actual attempts without raw error bodies.
Valid model NONE ends successfully without trying other characters. Cancellation propagates.

`DirectorProvider.complete()` must mean **one physical attempt**, without hidden retries or paid
fallback. Provider identity is supplied by trusted adapter code, never model output. Production
integration must reuse the existing Utility Gateway/Free Token Pool, including its credential,
quota and admission checks. **That adapter and production entry wiring are not implemented here.**
The test provider is explicitly a stub; these tests do not prove a real provider's latency/quality.

## Three-arm comparison

The `rules` command actually executes arm B. The `compare` command accepts normalized JSONL
`ReplayRecord` captures for A (current planner), B (rules), and C (rules + Director). Use each real
adapter to produce captures; the harness never creates A/C outputs from expected labels. Until
those adapters/runs exist, their arms are reported missing rather than fabricated.

Each capture binds case/dataset hashes, source commit, run ID, execution kind and source revision.
Each arm in one report must have one run/source/execution identity. Repetitions/model variants need
separate reports. Duplicate predictions, foreign cases, stale revisions and conversation/family
leakage across calibration/heldout are rejected. A SHA is provenance metadata, not independent
proof that the declared source generated the record; retain command/model/provider evidence too.

Labels allow alternative complete speaker/target sets. Empty means successful NONE. Operational
errors never receive NONE credit. Mixed silence-or-speech cases are excluded from binary NONE
precision/recall and counted separately. Missing predictions reduce coverage and joint accuracy;
an entirely missing arm has unknown accuracy. Direct-pair misses measure **admission**, not whether
Character ultimately answered or whether Discord delivered it.

Unknown usage, auxiliary work and cost stay unknown, not zero. Known cost subtotals are lower
bounds. Report physical provider attempts separately from logical Director decisions and buffered
events. Auxiliary token/cost fields must cover any non-Director compute in a captured arm. Latency
percentiles are for observed samples only; inspect sample coverage. No dollar savings, naturalness
or complete resource-cost conclusion follows from this routing-only report.

## Remaining promotion gate

`promotion_approved` is always false: this tool does not grant release authority. Expand and obtain
human review of a versioned 200-500-point corpus, freeze conversation/family heldout groups, run
actual pinned A/B/C implementations, and review quality, all-attempt cost/latency and end-to-end
Character/tool/delivery behavior. Set acceptance thresholds after baseline measurement and before
heldout candidate evaluation. Production wiring, negative isolation tests and independent/human
review remain separately visible. Existing production is unchanged during this offline spike.
