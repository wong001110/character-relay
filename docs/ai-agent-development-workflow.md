# Character Relay — AI Agent Development Workflow

Status: **required workflow for AI-assisted coding**

Character Relay is developed with multiple AI coding agents and parallel branches. The primary risk is not only code defects; it is **context drift**: an agent may confidently invent an endpoint, assume an old architecture is current, apply a proposal that was never accepted, or treat generated UI copy as real product data.

This workflow adds an OpenWiki-backed orientation layer while keeping code, tests, contracts, and accepted decision/status documents authoritative.

---

## 1. Source-of-truth hierarchy

Use this hierarchy instead of relying on chat memory:

### Implemented behavior

1. Current branch source code, schemas/types, migrations, and tests.
2. Current `main` source when determining the merged baseline.
3. Canonical implementation/status/decision docs explicitly referenced by the task.
4. OpenWiki-generated documentation as a navigation/synthesis layer.
5. PR discussion, issue text, or conversation memory.

### Intended architecture / UI direction

1. Accepted decision/contract/status documents in `docs/`.
2. Approved UI reference + `docs/ui-page-migration-plan.md` for visual composition only.
3. Current code/tests for what is actually possible today.
4. OpenWiki synthesis.
5. Proposal docs / old PR descriptions / chat memory.

If sources conflict, **do not reconcile by guessing**. State the conflict and choose the source whose authority matches the question (implemented behavior vs intended direction), or stop for review when the conflict changes product behavior.

---

## 2. OpenWiki's role

OpenWiki is used to maintain a navigable, agent-oriented wiki for the repository. Its job is to help an agent answer:

- What is this subsystem?
- Which files own it?
- What is authoritative data vs derived state?
- What decisions are already accepted?
- What is implemented vs planned?
- Which tests prove the behavior?
- Where should the next change be made?

OpenWiki is **not** an independent source of product truth. Generated pages can be stale or synthesize source material incorrectly; agents must trace claims back to code/tests/canonical docs before changing behavior.

The persistent generation brief lives in `openwiki/INSTRUCTIONS.md`.

---

## 3. Start-of-task protocol

Every AI coding session should follow this sequence.

### A. Establish branch context

Record:

- repository and branch;
- base branch / merge-base when relevant;
- current task/PR scope;
- whether the task is implementing merged behavior or stacked/unmerged work.

If `docs/active-development-plan.md` exists and names the current branch, read it before planning implementation. Confirm its current phase against Git and repository evidence; update stale status instead of following it blindly.

Never assume an open PR is already on `main`.

### B. Orient through OpenWiki

If `openwiki/quickstart.md` exists:

1. read it;
2. follow only the pages relevant to the task;
3. collect source-file links named by the wiki.

If generated OpenWiki pages do not exist yet, use `docs/agent-handoff.md`, `docs/README.md`, and the canonical docs directly. `openwiki/INSTRUCTIONS.md` is the generation brief, not a substitute generated quickstart.

### C. Verify at the source

Before implementation, inspect the exact:

- components/modules;
- API/type contracts;
- storage/schema objects;
- tests;
- accepted decision/status docs;
- approved UI reference for an approved UI page.

The agent should be able to name the source paths supporting its plan. If it cannot, it is not ready to code.

### D. Define invariants

Write down what must not change. Examples:

- Runtime owns authority/scope/security decisions;
- Character Roleplay retains the agreed semantic autonomy;
- Discord-native chat cannot be reskinned;
- UI references cannot invent data;
- credentials must never leak to browser-visible logs or docs;
- Server-scoped knowledge/intelligence must not become global by accident.

---

## 4. Phased delivery, validation, and delegation

Long-lived or cross-cutting branches use `docs/active-development-plan.md` as a branch-local execution ledger. It must state the approved scope, evidence map, invariants, phase statuses, validation gates, and work left for the next agent. It records active work; it is not a new source of product authority.

### Batch size and commit cadence

- Group related source, schema, test, and canonical-document changes into one coherent phase batch.
- Do not create a commit for each file, small refactor, or intermediate test repair.
- During implementation, use the smallest checks that provide useful feedback after a coherent batch; do not rerun the full repository suite after every edit.
- At the end of the phase, run the complete validation named by its gate, repair failures, review the integrated diff, then create at most one implementation commit for that phase.
- A failed check is not a commit boundary. Keep the phase uncommitted until its gate passes or is explicitly recorded as blocked.
- The final branch gate still requires the relevant cross-project checks even when each phase passed its own targeted suite.

Read-only investigation may happen throughout a phase. A targeted test may be run earlier when needed to reproduce a defect or protect a risky migration, but routine micro-validation should not replace the batch cadence.

### Sub-agent delegation

The main agent may delegate bounded, independently reviewable work such as research, source mapping, verification, test execution, or edits in an explicitly assigned file set. Delegation does not transfer integration authority.

The main agent must:

- give each sub-agent the current phase, evidence, invariants, allowed files, and expected output;
- avoid overlapping edit ownership in the shared worktree;
- reconcile conflicting findings against source and canonical contracts;
- inspect all delegated diffs and test results;
- integrate validation and create the phase's single implementation commit;
- record material findings and remaining work in the active plan.

Sub-agents should not commit shared-tree changes independently unless a separate branch/commit boundary is explicitly assigned.

---

## 5. Hallucination guards during implementation

AI agents MUST NOT:

- invent API fields, endpoints, database columns, environment variables, statuses, limits, or metrics;
- copy literal sample values from a generated UI reference into production behavior;
- assume an old roadmap section is implemented without checking current code/status;
- silently merge mutually inconsistent architectural proposals;
- treat a previous chat answer as stronger evidence than repository sources;
- widen Discord server/user/character data scope because a wiki summary is vague;
- expose secrets, provider keys, credential values, or secret-derived data in OpenWiki pages;
- rewrite unrelated feature logic in a visual/UI PR;
- update generated OpenWiki pages manually as if they were canonical source documents.

When uncertain, the agent should surface the missing source instead of filling the gap with a plausible guess.

---

## 6. Evidence map for every non-trivial PR

The PR description should include a compact evidence map:

- **Canonical docs read:** exact paths.
- **Source contracts inspected:** exact code/type/schema paths.
- **Tests relied on/added:** exact paths or test names.
- **UI reference:** exact file when applicable.
- **Intentional deviations:** what differs from the reference/plan and why.
- **Out of scope:** adjacent behavior deliberately not changed.

This gives the next agent a traceable chain back to source instead of requiring it to reconstruct intent from commit history.

---

## 7. Canonical docs vs generated wiki

Keep two layers deliberately separate.

### Canonical/manual layer

Examples:

- architecture/decision contracts;
- status/roadmap documents;
- UI/UX contract and approved UI plan;
- security/runtime authority rules;
- `openwiki/INSTRUCTIONS.md`.

Humans/agents edit these intentionally when decisions change.

### Generated OpenWiki layer

`openwiki/` pages generated by OpenWiki summarize and connect the repository. Treat them as disposable/rebuildable documentation.

Do not put a critical product decision only in a generated page. Put the decision in a canonical document and let OpenWiki link/summarize it.

---

## 8. OpenWiki operating cycle

Once OpenWiki is installed/configured for the chosen provider/model:

### First repository generation

```bash
openwiki --init
```

Review the generated diff before committing it.

Do not hand-write `openwiki/quickstart.md` to imitate generator output. When the CLI/provider is unavailable, keep the manually maintained takeover path in `docs/agent-handoff.md` current and report that generation was not run.

### Refresh after merged architectural work

```bash
openwiki --update
```

### CI / non-interactive inspection mode

```bash
openwiki code --update --print
```

Use upstream OpenWiki documentation for provider/model configuration rather than hard-coding one vendor into Character Relay.

### Parallel-branch policy

Do **not** regenerate the whole wiki independently in every feature branch. That creates noisy conflicts and allows an unmerged branch to masquerade as repository truth.

Preferred cycle:

1. feature PR changes code + canonical docs/status as needed;
2. feature PR is reviewed/merged;
3. a dedicated docs/OpenWiki refresh branch runs against updated `main`;
4. review OpenWiki changes for hallucinated/stale claims;
5. merge the documentation refresh separately.

For a long-lived stacked branch, the branch's PR body remains the active-work record. OpenWiki represents the merged baseline unless a branch-local refresh is explicitly requested and clearly labelled.

---

## 9. What OpenWiki should make easy to trace

The generated wiki should provide source-and-test-linked maps for:

- repository architecture and service boundaries;
- Discord connector flow and deployment/server scope;
- Character Card / Prompt / Runtime / Credential ownership;
- Intelligence Core v3 Conversation Structure / Episode / Belief / Context Resolver / Participation Planner flows, with obsolete Topic authority clearly forbidden;
- Media Understanding and media dependency/perception boundaries;
- Memory / RAG / Knowledge / Wiki / Graph distinctions;
- Tool ownership: internal context tools vs external capability tools vs runtime-required operations;
- Provider calls and observability/traces;
- scheduling/reminders;
- UI architecture, shared components, approved UI references, and overlay hierarchy;
- testing, CI, deployment, and manual validation;
- current roadmap/status documents with clear implemented/planned/deprecated markers.

Every major generated explanation should name the source paths that support it.

---

## 10. UI-specific agent workflow

For approved UI renovation pages:

1. Read `docs/ui-page-migration-plan.md`.
2. Open the approved `docs/ui-references/*.webp` image.
3. Inspect current page code and its API/types.
4. Separate **visual composition** from **sample content in the generated image**.
5. Build a real-data mapping before JSX/CSS changes.
6. Preserve accessibility, responsive behavior, and overlay layer rules.
7. If a needed metric does not exist, do not fabricate it; document the missing contract.
8. Update `/dev/ui` when adding reusable components or variants.

---

## 11. End-of-task protocol

Before declaring work complete:

- run relevant typecheck/tests/build/lint;
- review diff for unrelated changes;
- confirm no secrets or generated credentials are present;
- update canonical status/decision docs if behavior/architecture changed;
- update the active development plan's phase status, validation evidence, commit, and next takeover point when it applies;
- record evidence and deviations in the PR;
- if the change is merged architecture, schedule/perform an OpenWiki refresh against `main` rather than assuming the existing wiki is current.

The goal is that a future agent can answer **"why is this here, what owns it, and where is the proof?"** without relying on the previous agent's memory.
