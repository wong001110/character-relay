# Change acceptance checklist

Reusable evidence checklist, **not a second project status tracker**.
Current progress belongs in [PROJECT_STATE.md](PROJECT_STATE.md); policy is [AGENTS.md](AGENTS.md).
Old phase-completion claims are retained in Git history, not used as current acceptance evidence.

- [ ] Change matches the user's permitted scope; implementation and proposals are clearly separated.
- [ ] Baseline/branch and actual owning source/contracts were checked; no unrelated work was included.
- [ ] Relevant checks have commands, results and evidence tied to the tested revision.
- [ ] Positive journeys and meaningful negative cases protect the changed behavior.
- [ ] Changed trust/effect boundaries have targeted security/fault and applicable mutation evidence.
- [ ] Integrated diff reviewed; self-review and independent review are labeled honestly.
- [ ] Replaced runtime consumers, config, prompts, routes and docs are removed or explicitly blocked.
- [ ] No credentials/raw private data; disclosure, retention and history policies are preserved.
- [ ] PROJECT_STATE, affected ownership map and accepted-plan coverage reflect actual work.
- [ ] Unrun live checks, new recurring costs, migration risk and release blockers are explicit.

For documentation-only PRs, source/behavior/security execution items may be not applicable with a
reason: verify changed paths, links, status consistency and unchanged runtime trees instead. Do not
report application tests as passed when not executed. This checklist does not authorize deployment,
production mutation or merge.
