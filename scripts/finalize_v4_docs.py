from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected documentation block not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


roadmap = "docs/conversation-intelligence-v4-roadmap.md"
replace_once(
    roadmap,
    "Status: **PLANNED / implementation branch opened**",
    "Status: **IMPLEMENTED / RELEASE VALIDATED IN DRAFT PR #166**",
)
replace_once(
    roadmap,
    "Delivery rule: **all work in this roadmap stays in one Draft PR until final validation and explicit merge approval.** Do not split Turn Collector, participation pipeline reorder, conversation-aware resolution, Graph shadow mode, Graph reranking, Character Learned State, Topic/Media integration, or final rollout into separate implementation PRs.\n\n## Goal",
    """Delivery rule: **all work in this roadmap stays in one Draft PR until final validation and explicit merge approval.** Do not split Turn Collector, participation pipeline reorder, conversation-aware resolution, Graph shadow mode, Graph reranking, Character Learned State, Topic/Media integration, or final rollout into separate implementation PRs.

## Implementation result

Phases 0–8 are implemented on `agent/conversation-intelligence-v4` in Draft PR #166.

Release validation completed against commit `4591f3c405136fd1c072837175b1a70e2dc07827`:

- **CI #1314:** green — Python 3.12/3.13 Ruff, strict Mypy and full Pytest; Web typecheck/tests/build; Discord Connector typecheck/tests/build/image; production Docker persistence and smoke checks.
- **Railway Smoke #1280:** green.
- Final guarded Connector edge validation passed **126 / 126 Vitest tests**, Python Media provenance tests, strict Mypy, Connector build, and `git diff --check`.
- Durable low-information recovery now restores a recent Smart speaker after Connector process-state loss without adding a request to the normal hot path.
- Pure visible-image bursts preserve the original Discord image-message ID through Media perception, Conversation Media, and Graph provenance; URL/video inspection policy remains Tool-driven.
- The Public Demo Status workflow remains red because the deployed demo has 5 Characters but only 3 ready credentials. The same workflow is red on current `main`, so this is recorded as a pre-existing deployment/configuration issue rather than a V4 runtime regression.

The PR remains **Draft and unmerged**. Runtime rollout remains independently disableable/shadowable and merge still requires explicit owner approval.

## Goal""",
)

product = "docs/product-roadmap-rag-and-smart-participation.md"
replace_once(
    product,
    "This document records the current runtime boundaries and the next major runtime milestone for Discord Smart Participation, Context/Topic/Memory, Media Understanding, RAG/Wiki, Tool Calling, and System Intelligence.",
    "This document records the current runtime boundaries and the implemented Smart Participation V4 / Conversation Intelligence milestone for Discord Smart Participation, Context/Topic/Memory, Media Understanding, RAG/Wiki, Tool Calling, and System Intelligence.",
)
replace_once(
    product,
    "Detailed V4 implementation planning lives in `docs/conversation-intelligence-v4-roadmap.md`.",
    "Detailed V4 architecture and implementation history lives in `docs/conversation-intelligence-v4-roadmap.md`; release evidence lives in `docs/conversation-intelligence-v4-validation.md`.",
)
replace_once(
    product,
    "## 8. Next major milestone — Smart Participation V4 / Conversation Intelligence Graph\n\nV4 is the next major selection/runtime integration project.",
    "## 8. Current milestone — Smart Participation V4 / Conversation Intelligence Graph\n\nV4 is implemented in Draft PR #166 and release-validated for CI/Railway. The runtime remains feature-flagged and shadowable so Graph/Learned-State influence can be rolled out conservatively without weakening explicit or deterministic authority.",
)
replace_once(
    product,
    "## 9. V4 delivery sequence — one PR\n\nThe V4 Draft PR owns the whole sequence:",
    "## 9. V4 delivery sequence — one PR\n\nThe V4 Draft PR completed the sequence as one coherent implementation:",
)
replace_once(
    product,
    "The PR may ship with Graph reranking disabled if Turn Collector/pipeline/resolver improvements are proven useful but Graph benefit is not yet strong enough. Graph must remain a removable derived layer.",
    "Production rollout may keep Graph/Learned-State reranking in shadow or disabled mode until live outcome evidence justifies activation. Graph remains a removable derived layer and does not own authoritative conversation/media truth.",
)
