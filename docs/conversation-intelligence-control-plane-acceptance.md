# Conversation Intelligence Control Plane — Acceptance Checklist

Status: **historical branch acceptance record — not current runtime authority**

PR: #187  
Branch: `agent/conversation-intelligence-control-plane`

This checklist is intentionally written for one final end-to-end acceptance pass rather than per-phase approval.

## Phase 0 — Baseline and safety contracts

Status: implemented

- Raw Discord source evidence remains outside destructive derived-data cleanup.
- Topic/Memory/Graph mutation boundaries are explicit and owner-scoped.
- New observation data is stored in dedicated derived tables or sidecars.

## Phase 1 — Data Hygiene and Governance

Status: implemented

Verify:
- preview Topic delete impact before deletion;
- archive one Topic;
- hard-delete polluted Topic-derived intelligence;
- reset one Character × Server synthesized Memory scope;
- invalidate/delete one synthesized Memory;
- confirm raw Discord source evidence remains;
- confirm explicit Core Memory survives Topic/synthesized resets.

Cleanup covers Topic/Episode projections, synthesized Memories derived from those Episodes, Wiki, authority graph, Topic graph projection, Topic learned-state history, consolidation checkpoints, semantic vectors, Topic decision traces, SQL-RAG incidence/access records, and orphaned entities.

## Phase 2 — Topic Lifecycle and Decision Observatory

Status: implemented

Verify:
- Topic lifecycle advances instead of leaving stale Topics active indefinitely;
- decision trace explains continue/switch/resume/create/lifecycle;
- dense/sparse/continuation/switch scores are visible;
- Tool Continuation and Topic observation reuse one continuity decision;
- display label remains stable while semantic Topic identity evolves from rolling summary/keywords.

## Phase 3 — Interaction Grounding

Status: implemented

Regression cases:
- profession-related ambient group chat defaults to peer-group posture;
- a Character profession/background can raise relevance without implying the Character is being questioned;
- explicit mention/reply/name addressing remains direct;
- explicit group invitation is distinguished from ambient discussion;
- profession/group-directed wording is distinguished from personal address;
- only pragmatic gray zones are eligible for Utility/LLM escalation.

## Phase 4 — Episodic SQL-RAG

Status: implemented

Verify:
- Episode is the event/evidence unit;
- deterministic entities are indexed immediately;
- `CharacterEpisodeAccess` restricts recall to Episodes the Character actually perceived;
- E5/sparse retrieval finds seed Episodes;
- bounded SQL event → entity → event joins expand only informative entity types;
- high-degree/common entities cannot explode retrieval;
- current trigger Episode is excluded from historical auto-recall;
- Retrieval Preview shows seed/expanded Episodes and entity neighborhoods without calling the Character model.

## Phase 5 — Layered Memory

Status: implemented

Layers:
- Working context: recent conversation/current Topic/pending action.
- Core Memory: explicit user-controlled durable memory.
- Synthesized Memory: background consolidation with provenance/merge/supersede semantics.
- Episodic History: perception-safe SQL-RAG retrieval.
- Learned State: interest/relationship/expertise/stance/salience/ownership/fatigue.
- Memory Summary: versioned rebuildable cache.

Verify:
- create/edit/archive/delete Core Memory;
- promote synthesized Memory to Core;
- inspect Core revision history and restore a revision;
- synthesized freshness is metadata, not destructive authority;
- stale synthesized Memory is excluded from automatic prompt recall;
- Memory Summary versions only when its source set/content changes;
- background consolidation refreshes synthesized freshness and Character × Server summary without a second worker or extra LLM call.

## Phase 6 — Unified Character Recall

Status: implemented

Verify:
- `memory.search` searches Core + synthesized layers;
- Core wins exact-content duplicate arbitration;
- `conversation.search` uses perception-safe E5 seed + SQL expansion;
- automatic recall remains tiny/high-confidence only;
- high-priority Core may auto-recall;
- synthesized Memory requires high semantic/confidence/importance thresholds;
- episodic auto-recall requires explicit historical cues;
- current message is never retrieved as its own historical memory;
- memory prompt block is bounded and explicitly treated as data, not instructions;
- deep recall remains available through Internal Context Tools.

## Phase 7 — Character Mind and Social Graph

Status: implemented

Verify:
- short-lived NOW state is separated from slower interest/expertise/stance state;
- append-only evidence history explains value-before/value-after/delta/confidence/source/reason;
- Current Interest is derived from server-scoped evidence history and shows trend;
- Social Graph is an ego graph rather than a global hairball;
- Character↔Character identity uses known Discord message/deployment routing rather than display-name guessing;
- relationship edges expose strength/confidence/evidence/recency.

## Phase 8 — Portal Observation and Controls

Status: implemented, final visual acceptance pending

Index tabs:
- Overview
- Topics
- Memories
- Character Mind
- Social Graph
- Data Hygiene

Verify:
- Topic status counts and stale-active warning are understandable at a glance;
- Topic decision timeline explains transitions;
- Core and synthesized Memory are visually distinct;
- destructive actions require an impact/confirmation path;
- Character Mind no longer renders every state as one undifferentiated meter;
- Social Graph remains bounded/readable;
- Memory revision/freshness/summary and Retrieval Preview endpoints are reachable under the Conversation Intelligence prefix.

## Phase 9 — Calibration, rollout, and acceptance

Status: implementation complete; validation gate in progress

Required gate:
- Python compile
- Ruff
- Mypy
- full pytest suite
- focused Conversation Intelligence regressions
- Web production build
- GitHub CI / Railway smoke / public demo checks

Final product acceptance should focus on:
1. polluted Topic/Memory data can be safely repaired;
2. Topic switching/lifecycle is explainable;
3. ordinary profession-related group chat no longer frames the Character as being interrogated;
4. Core/Synthesized/Episodic memory responsibilities are understandable;
5. Character recall respects perception boundaries;
6. current interest and social relationships are explainable over time;
7. Utility/LLM Judge remains a bounded low-frequency ambiguity resolver.
