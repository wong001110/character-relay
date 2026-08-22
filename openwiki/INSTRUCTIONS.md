# Character Relay OpenWiki instructions

This is the persistent human-authored generation brief. Generated pages are disposable orientation; they never replace source, tests, schemas, migrations, or accepted contracts.

## Reader and outcome

Generate a concise wiki for an AI coding agent arriving with no chat history. Within a few minutes the agent should be able to identify:

- the merged baseline and service boundaries;
- which module owns a behavior and which tests prove it;
- authoritative, derived, rebuildable, and turn-local state;
- implemented versus planned, experimental, deprecated, or branch-only work;
- security/scope invariants and forbidden compatibility paths;
- the smallest relevant validation commands.

Create `openwiki/quickstart.md` as the entry point and link outward to small source-backed pages. Do not repeat long roadmaps or produce one page per source file.

## Mandatory grounding

- Prefer current merged `main` behavior unless a page is explicitly and visibly branch-local.
- Link exact repository paths for every important behavioral claim and name the proving tests.
- Read `docs/README.md`, `docs/agent-handoff.md`, `docs/architecture.md`, and task-relevant canonical contracts before interpreting roadmaps/status files.
- A branch name, checked checklist, release note, or PR number is historical evidence, not proof that code is on `main`.
- When sources conflict, show the conflict and paths; never invent a reconciliation.
- Do not include secrets, tokens, credentials, private provider payloads, raw private transcripts, or secret-derived values.
- Generated UI reference art controls composition only. Never infer fields, metrics, limits, copy, or backend behavior from it.

## Source authority

For implemented behavior:

1. current source, schemas/types, migrations, and tests;
2. current `main` baseline;
3. task-relevant accepted contracts/status/decision docs;
4. generated wiki synthesis;
5. proposals, PR text, issue text, and chat memory.

For intended architecture/UI direction, accepted contracts/decisions lead, but do not imply implementation. Label every planned feature accordingly.

## Required quickstart contents

Keep `quickstart.md` short and source-linked:

1. product/service summary;
2. current Git baseline and generation timestamp;
3. repository/module map;
4. top authority and security invariants;
5. current Intelligence Core v3 hard-cutover warning;
6. start/test/build commands traced to package/workflow files;
7. links to subsystem pages and canonical docs;
8. known conflicts or stale documents discovered during generation.

Never freeze unstable live CI, issue, PR, or deployment status as “current” without a timestamp and source.

## Required subsystem maps

Generate only source-linked pages needed to cover:

1. API/application composition, authentication, ownership, credentials, and Public Demo read-only enforcement.
2. Character lifecycle: Card -> Prompt/Model -> Credential -> Test -> Deployment.
3. Discord Connector: Gateway ingress, server/deployment identity, Smart Participation, Social Turn, tools/media, and durable delivery.
4. Intelligence Core v3: relations/segments/threads, Episodes, Entity/Evidence Graph, Beliefs, Social/Behavior State, Context Resolver, and Participation Planner.
5. Media epistemics: objective perception, planner-only information, Character-visible context, cache/provenance, and generated-media delivery.
6. Knowledge/RAG/Wiki and which state is authoritative, derived, rebuildable, and scoped.
7. Tool categories: internal context, external capability, and runtime-required operations.
8. Runtime/Provider observability and failure isolation.
9. Evaluation/authoring/calibration and human approval boundaries.
10. Portal architecture, shared components, approved references, and actual migration status.
11. Testing, CI, Docker/Railway deployment, storage, and manual acceptance.

Each subsystem page should end with “change here”, “proof”, “invariants”, and “related canonical docs”.

## Intelligence Core hard-cutover guard

`docs/intelligence-core-v3-architecture.md` is the canonical intelligence contract. Do not describe Topic as current authority or recommend any of the following:

- Topic runtime/lifecycle fallback;
- Topic compatibility UI or `topic.search`;
- `topic_id` as Memory, Episode, RAG, Tool, or continuation authority;
- Topic-scoped durable Memory or Topic Wiki identity;
- Topic-driven Discovery, Pending Action, or Episode formation.

Historical V3/V4/Topic documents may explain prior decisions but must be labelled superseded when they conflict with the v3 contract and current source/tests.

## UI reference rule

For approved UI pages, state explicitly:

- reference images govern composition, hierarchy, and visual intensity;
- current code/API/types/tests govern data and behavior;
- literal generated sample content is not an implementation requirement.

## Generation and review

- Represent merged `main`; active branch intent stays in its PR/evidence map.
- If branch-local generation is explicitly requested, label every generated page branch-local and do not merge it as baseline accidentally.
- Do not preserve generated prose solely to avoid diffs. Regenerate from sources.
- Review generated output for hallucinated endpoints/settings/status, scope widening, secrets, obsolete Topic authority, and broken source links before committing.
- After accepted architectural work merges, refresh from updated `main` in a dedicated docs pass.
