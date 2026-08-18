# Stabilization vNext — Implementation & Owner Acceptance

Branch: `agent/stabilization-vnext`  
PR: `#190`  
Status: **implementation complete through Phase 6; automated validation in progress; owner acceptance pending**

This document is the handoff/acceptance record for `docs/stabilization-vnext-roadmap.md`.

## Implemented phase summary

### Phase 1 — Provider Capability & Structured Output Hardening

- [x] Runtime-observed model capability registry separates model protocol/modality support from Character Relay consumer capabilities.
- [x] Provider failure classifier uses HTTP status + headers + JSON error body rather than treating HTTP 429 as the only quota signal.
- [x] 2xx error envelopes are classified before chat-completion parsing.
- [x] Quota/free-tier/billing/balance/auth/model/capability failures are normalized separately.
- [x] Media Understanding uses JSON Schema -> JSON Object -> prompt-only fallback based on observed capability.
- [x] Media parser safely extracts JSON surrounded by prose and normalizes serialization-only shape defects without inventing media facts.
- [x] Media Free Pool failures feed shared Utility provider health/quota state.
- [x] Capability mismatch does not globally poison a model that remains valid for text Utility work.

### Phase 2 — Discovery Product Surface

- [x] Deployment-level Discovery master control is exposed in Portal.
- [x] New/current default semantics remain Discovery OFF with YouTube/Bilibili disabled until the owner opts in.
- [x] YouTube and Bilibili are independently selectable sources.
- [x] Bilibili remains gated by the global Experimental switch.
- [x] Shadow / Review / Auto and per-Deployment Auto/budget/cooldown controls are exposed.
- [x] Portal observatory exposes sessions, browse funnel, exposures/perception, decisions/evidence, and shares/review actions.

### Phase 3 — Burst Segmentation + Semantic Threads

- [x] Conversation Burst remains a temporal collection unit, not one Topic.
- [x] One Burst may project multiple Conversation Segments.
- [x] Explicit reply links are treated as strong structural evidence.
- [x] Multiple concurrent Semantic Threads may remain HOT/WARM/DORMANT without exclusive Active Topic authority.
- [x] Segment assignment and `thread_evidence` are separate.
- [x] Context-only/reaction segments do not broaden Thread identity.
- [x] Existing V4 Smart Participation remains admission authority during compatibility migration.
- [x] Utility Judge is used for complex Burst structure when available; deterministic fallback remains available.

### Phase 4 — Segment Reply Planner

- [x] Each admitted Character chooses one primary Segment by default.
- [x] Character semantic participation relevance and direct-address pressure influence Segment selection.
- [x] Selected Segment guidance flows through the existing `participation_guidance` path into Roleplay.
- [x] Guidance explicitly avoids summarizing/responding to unrelated simultaneous discussions.
- [x] Existing Discord visible-message execution remains bounded by the current speaker plan.

### Phase 5 — Relationship / Social Intelligence v2

- [x] Existing single learned relationship scalar remains only as compatibility/familiarity evidence.
- [x] New lived dimensions are Familiarity / Affinity / Trust / Comfort.
- [x] Ordinary direct interaction only increases Familiarity.
- [x] Character Card-level directional Canonical Relationship Prior exists.
- [x] AI can generate reviewable Starting Dynamics; generated values are not silently persisted.
- [x] Same-Server Character Deployments can explicitly initialize lived state from the canonical prior.
- [x] Dynamic deltas decay toward canonical baselines rather than toward stranger/zero state.
- [x] Bot-to-Bot targets resolve to Deployment identity when a Character message route is available.
- [x] Person Impression is stored separately from Memory and Relationship State.
- [x] Bounded Social Context is injected only for the current interaction target.
- [x] Portal provides Generate Starting Dynamics / Save Prior / Initialize for this Server and current-state inspection.

### Phase 6 — Integrated observability

- [x] Deployment Portal exposes concurrent Semantic Threads and recent Conversation Segments.
- [x] Conversation structure observability works at Server scope for server-wide Deployments.
- [x] Discovery, Relationship, and Conversation Structure are visible from the existing Deployment work surface.
- [x] New regression tests cover provider semantics, structured media output, interleaved Burst segmentation, reply targeting, canonical relationship initialization, baseline delta behavior, and bounded Social Context.

## Automated validation gate

Latest validation is intentionally tracked separately from implementation state.

- [ ] Ruff — Python 3.12
- [ ] Ruff — Python 3.13
- [ ] MyPy — Python 3.12
- [ ] MyPy — Python 3.13
- [ ] Full Pytest — Python 3.12
- [ ] Full Pytest — Python 3.13
- [ ] Web typecheck / tests / build
- [ ] Discord Connector typecheck / tests / build / image
- [ ] Production Docker persistence/health/smoke
- [ ] Railway Smoke

## Owner acceptance checklist

### Provider / Media

1. Exhaust a provider whose API returns a non-429 quota/billing JSON and confirm the Free Pool stops retrying it incorrectly.
2. Use one text-only model incorrectly tagged for Media and confirm media routing skips/learns the modality failure without disabling its text Judge use.
3. Exercise a Vision model that returns fenced/prose-wrapped or slightly malformed JSON and confirm safe serialization repair preserves the useful perception result.
4. Confirm unsupported JSON Schema falls back to JSON Object/prompt-only without repeated future schema attempts for the same model endpoint.

### Discovery

5. Confirm a newly configured Deployment has Discovery OFF and no source selected.
6. Enable only YouTube for one Deployment and confirm another Deployment remains independently disabled or Bilibili-only.
7. Inspect browsing sessions and verify SCROLL/NOTICE/OPEN/WATCH/ENGAGE evidence is visible.
8. Exercise REVIEW approve/reject and verify AUTO remains governed by both Deployment and global gates.

### Conversation model

9. Send one Burst containing two interleaved reply chains and confirm the observatory shows two Segments/Threads rather than alternating Topic switches.
10. Send a short reaction such as `哈哈` and verify it may belong to context but does not update Thread identity evidence.
11. Confirm one Character selects one relevant Segment and does not reply to every simultaneous subject in the Burst.

### Relationship / Social Intelligence

12. Define a directional canonical Bot-to-Bot relationship, generate Starting Dynamics, review/edit it, save it, then initialize it for one Server.
13. Confirm the reverse direction can have different Starting Dynamics.
14. Confirm ordinary repeated interaction increases Familiarity without automatically increasing Affinity/Trust/Comfort.
15. Add a meaningful negative dynamic event and confirm the state moves away from baseline, then decays back toward the canonical baseline rather than zero.
16. Confirm the Roleplay prompt receives a compact natural-language Social Context for the current target, not the entire Social Graph or raw score dump.

## Merge policy

Keep PR #190 Draft until the owner completes product acceptance. Do not auto-merge after green CI.
