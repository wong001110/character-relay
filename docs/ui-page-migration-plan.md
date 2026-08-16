# Character Relay — UI Renovation Plan

Status: **approved visual direction + implementation contract**

This document is the page-level source of truth for the Character Relay web UI renovation. It supersedes the earlier "scrapbook skin" interpretation: future work must change page composition and information hierarchy where an approved reference requires it, not merely recolor existing admin layouts.

The product remains an **Anime Scrapbook Workspace**: characters provide the strongest anime identity; paper, index flags, notes, stamps, tape, and annotations provide the scrapbook frame. Functional behavior, real data, accessibility, and technical readability remain authoritative.

Related contracts:

- `docs/ui-ux-contract.md`
- `docs/ui-component-library.md`
- `docs/ai-agent-development-workflow.md`
- `AGENTS.md`

---

## 1. Mandatory execution protocol for AI coding agents

For any UI task covered by this plan, an AI coding agent MUST do the following before editing code:

1. Read `AGENTS.md`.
2. Read `docs/ui-ux-contract.md` and `docs/ui-component-library.md`.
3. Read this plan and locate the exact page section.
4. Open the corresponding image in `docs/ui-references/` when the page is marked **APPROVED**.
5. Inspect the current feature component, related API/types, tests, and current `main`/branch diff.
6. Write down the real fields/endpoints/state that will drive the UI. Do not infer them from the reference image or prior chat memory.
7. Implement the smallest coherent page-composition change that preserves product behavior unless the plan explicitly calls for a structural navigation change.
8. Run the relevant web typecheck/tests/build and update canonical docs when the change alters architecture or page status.

### Reference-image authority

Approved images are **composition references**, not screenshots of a finished product contract.

They ARE authoritative for:

- page hierarchy and spatial composition;
- relative visual emphasis;
- scrapbook intensity;
- placement/use of PageFlags, StickyNotes, PaperCards, stamps, and portrait emphasis;
- the overall relationship between primary content and secondary technical content.

They are NOT authoritative for:

- literal numbers, timestamps, names, sample copy, server limits, metrics, or statuses shown inside generated art;
- API fields or endpoints;
- backend behavior;
- data that does not exist in current code;
- arbitrary decorative navigation that conflicts with the approved product navigation.

**Never implement invented data because it appears in generated reference art.** Current code/types/API/tests determine what can be rendered. If the reference needs information that is unavailable, either derive it from an existing authoritative source, add a separately reviewed data contract, or omit/degrade the element and document the deviation.

### Design-system rule

Feature pages should consume shared UI (`components/ui`) and Character Relay domain components (`components/shared`) rather than creating local copies. Functional icons remain deterministic SVG/CSS. Generated/raster art is allowed for organic illustration, character art, paper texture, empty states, and restrained scrapbook decoration.

---

## 2. Approved UI reference index

| Surface | Status | Reference | Implementation meaning |
| --- | --- | --- | --- |
| Dashboard | **APPROVED** | `docs/ui-references/dashboard.webp` | Research-studio overview grounded in live Character Relay state |
| Characters / Character Archive | **APPROVED** | `docs/ui-references/characters-archive.webp` | Character archive with portrait-first durable files |
| Character File | **APPROVED** | `docs/ui-references/character-file.webp` | Full-page, read-first single-character record |
| Character Creator | **APPROVED** | `docs/ui-references/character-creator.webp` | Full-page seven-page character-writing flow |
| Test Room | **APPROVED** | `docs/ui-references/test-room.webp` | Live character experiment with conversation-first observation |
| Deployment Workspace | **APPROVED** | `docs/ui-references/deployment-workspace.webp` | Server Passport + Server Notebook + character deployment files |

The images are intentionally optimized reference assets; the original generated images are not runtime dependencies.

---

# Approved page specifications

## 3. Global Shell

Status: **direction established by all approved references**.

- Keep one global top navigation: `Dashboard / Characters / Deployments / Toolbox / Settings`.
- Do not add a second right-side global navigation.
- The shell stays relatively quiet; page identity lives in the content area.
- Replace decorative Unicode functional glyphs with a consistent icon system over time.
- Overlay order follows the semantic layer contract already introduced: page < drawer < modal < confirm < critical.

Scrapbook intensity: **low-medium**.

---

## 4. Dashboard — APPROVED

Reference: `docs/ui-references/dashboard.webp`

Visual role: **Character Research Studio / current-world overview**.

The Dashboard should answer three questions first:

1. Where are my characters now?
2. What just happened?
3. Does anything need my attention?

### Composition

- Hero: `CHARACTER RESEARCH STUDIO` and the product-facing line "今天想让谁去真实世界里说话？" / equivalent localized copy.
- Primary actions: create character; open behavior observer.
- Compact snapshot notes sourced from real data:
  - Character Files;
  - Active Deployments;
  - Servers Online;
  - Needs Attention.
- **Live on Discord** is the primary working area, showing character, Server/Channel, participation mode, status, and recent activity when available.
- **Recent Activity Journal** uses Discord connector logs/events as a readable activity journal rather than a raw log table.
- Right-side semantic StickyNotes:
  - Attention Notes (deployment/connection/reminder/runtime issues that really exist);
  - Upcoming (pending scheduler reminders).
- Character Files provides compact quick entry to a few relevant characters.
- Bottom System Note is intentionally quiet: Judge / Adaptive / Discord readiness.

### Grounding constraints

Do **not** add fake global Success Rate, Test Session count, global Current Topic, storage percentage, or other generated-art metrics unless a real API/aggregate is added and reviewed. Topic state is scoped to server/channel/thread and must not be flattened into a fake global topic.

Scrapbook intensity: **medium-high**, with high identity but clear operational content.

---

## 5. Characters / Character Archive — APPROVED

Reference: `docs/ui-references/characters-archive.webp`

Visual role: **durable character archive / scrapbook shelf**.

### Composition

- Full page under the global navigation.
- `CHARACTER ARCHIVE / 角色档案册` identity area.
- Portrait is the strongest visual element on every Character file card.
- Real-data filters only:
  - All;
  - Deployed;
  - Not Deployed;
  - Needs Setup.
- Search behaves like finding a file, not operating a spreadsheet.
- Character cards show concise identity/persona and a few semantic tags.
- `Open File` is the primary action.
- Test/Deploy may remain compact shortcuts; Prompt/Memory/Runtime/portrait management should not compete on the shelf.
- The final blank card is `New Character File` and opens Character Creator.

### Grounding constraints

Do not add Favorites, Archived, Recently Edited, Last Edited, or other states until the data model actually supports them. `created_at` is not an `updated_at` substitute.

Scrapbook intensity: **high**.

---

## 6. Character File — APPROVED

Reference: `docs/ui-references/character-file.webp`

Visual role: **formal single-character record**.

This should become a full-page route/view, not the long-term home for a nested Drawer stack.

### Navigation

Vertical PageFlags:

- Profile
- Persona
- Prompt
- Memory
- Runtime
- Deployments

### Profile page

- Portrait + name + subtitle/subject type dominate.
- Persona summary and traits remain readable, not hidden behind edit controls.
- Current deployment/status appears as an attached status note.
- Preferred tests can appear as a structured secondary sheet where current data supports it.
- Top actions: `Test Character`, `Edit Character`, `Deploy` / open deployment.

### Secondary pages

- Persona: persona summary, traits, tone, forbidden behavior.
- Prompt: integrate Raw/Compiled prompt inspection into the file where feasible, reducing `Character File -> Prompt Modal` nesting.
- Memory: show configured/authoritative memory information only; do not invent vNext memory views before their contracts land on `main`.
- Runtime: provider/model/credential/readiness in a low-decoration technical sheet; editing routes to Character Creator/appropriate configuration.
- Deployments: show where this Character lives and open the corresponding Deployment file.

Scrapbook intensity: **medium-high**, lower than the archive around dense text.

---

## 7. Character Creator — APPROVED

Reference: `docs/ui-references/character-creator.webp`

Visual role: **actively writing/editing a Character file**.

The current controlled editor state supports true page navigation; future renovation should move the primary experience from `PaperDrawer` to a full-page editor.

### Seven pages

1. Identity
2. Persona
3. Voice
4. Boundaries
5. Memory
6. Runtime
7. Review

### Interaction rules

- Left PageFlags are real page navigation.
- Previous/Next provides a guided writing flow.
- Identity includes immediate Character/portrait preview and portrait palette/variant; upload/generation can be added later without becoming mandatory.
- Traits/Tags should migrate from newline-string editing toward direct chip/sticky-label editing where practical.
- Boundaries should read as an editable list of forbidden behaviors rather than a generic blob.
- Voice keeps long Prompt text readable; decoration is reduced around manuscript text.
- Memory stays limited to authoritative configured memory fields until richer memory contracts are on `main`.
- Runtime is intentionally much less decorative and keeps Provider/Base URL/Model/Temperature/API Key semantics clear.
- Review is a real final page: summarize completion/readiness and link validation failures back to the relevant PageFlag before save.

### AI Draft Assistant

- AI Draft is a side note/assistant, not the page's dominant form.
- It may fill Character-content fields, but never silently changes Provider or credentials and never auto-saves.
- AI-authored/changed pages should be visibly marked for human review.

Save should return to the Character File so the user sees the completed record.

Scrapbook intensity: **high overall; low-medium on Runtime**.

---

## 8. Test Room / Live Character Experiment — APPROVED

Reference: `docs/ui-references/test-room.webp`

Visual role: **live experiment notebook**.

### Three-part composition

- Left: compact Experiment Setup.
- Center: dominant Live Conversation / Trial event stream.
- Right: Observation Board.

### Setup uses current real semantics

- Character + readiness;
- Benchmark / Adaptive Tester;
- Rules / Semantic / Hybrid Judge;
- language;
- current test suites (Mirror / Memory / Script / Echo Hall mapping to real TestKind values);
- Watch / Fast observation mode;
- Begin/Stop Experiment.

Provider details should stay secondary unless credential/configuration is missing.

### Live conversation

- Tester and Character messages read primarily as conversation.
- Judge results are attached `JUDGE MEMO` notes, not fake chat participants.
- Breakpoints become visible red-pen experiment events without turning into blocking error modals.
- Keep transcript readability cleaner than the surrounding scrapbook surfaces.

### Observation Board

Use real run/result state for:

- Integrity / review state;
- evidence count;
- current room;
- first breakpoint/fracture;
- session state;
- Persona Note;
- benchmark comparison/regression state when available;
- Markdown Lab Note / JSON report after completion.

Scrapbook intensity: **medium-high around the experiment; medium-low inside transcript**.

---

## 9. Deployment Workspace — APPROVED / NEXT IMPLEMENTATION PRIORITY

Reference: `docs/ui-references/deployment-workspace.webp`

Visual role: **Server Workspace / field deployment manual**.

The primary context is the selected Discord Server, not a global connection-management dashboard.

### Server Passport

Top of page shows the selected Server with real available state:

- guild/server name and workspace/profile label;
- connector status;
- visible channel count;
- exclusions count;
- timezone when available;
- Character Relay Discord connection identity;
- `Server Settings` and `View Server Log` as secondary actions.

Connection infrastructure is summarized here; full connection management belongs in a Drawer/secondary flow, not a permanent main-column panel.

### Server Notebook

Use first-class PageFlags/Tabs:

- Characters
- Knowledge
- Interactions
- Intelligence

Only one notebook page is primary at a time.

### Characters page — default

Title: `CHARACTERS IN THIS SERVER`.

Compact real summary: total / active / paused / needs attention, plus synced channel count where available.

Each deployment reads as a **Character Deployment File** rather than a CRUD table, showing authoritative fields such as:

- portrait + Character name/subtitle;
- Presence / channel scope and exclusions;
- Participation mode;
- Memory scope;
- Discord identity mode/display name when available;
- enabled Tools count/details;
- status;
- last activity or last error when present;
- `Open Deployment`, Pause/Resume, compact secondary menu.

### Open Deployment

A Drawer/side sheet is appropriate because Server context should remain visible. Organize configuration into small sections/tabs such as:

- Presence
- Participation
- Identity
- Memory
- Tools

Participation modes should be explained as behavior choices rather than a cryptic select. Smart Participation links to the existing Studio rather than embedding every advanced parameter into this page.

Channel scope should express the existing model directly: default server-wide visibility with explicit exclusions where that is the authoritative deployment model.

### Knowledge / Interactions / Intelligence

These remain pages of the selected Server Notebook and inherit Server scope. They should not compete with Characters on the default page. Detailed page references may be approved later; existing functionality remains authoritative until then.

### Generated-art warning

The approved reference contains illustrative sample text/numbers. In particular, any depicted server Character limit, sample note, health metric, or count that does not exist in current code is **not** a requirement. The reference controls composition only.

Scrapbook intensity: **medium**, with stronger Server Passport/PageFlag identity and quieter configuration details.

---

# Existing surfaces that are acceptable / lower priority

## 10. Behavior Notebook

Status: **current direction acceptable; no new reference required now**.

Keep the current principle: **Narrative first -> Trace second**. Behavior / Flow / State / Raw, evidence expansion, provider receipts, and InspectorSection hierarchy can remain unless a concrete usability issue is identified.

Scrapbook intensity: medium for narrative, low for raw evidence.

## 11. Prompt Inspector

Short term: keep the current manuscript treatment. Long term, migrate its primary Raw/Compiled view into Character File -> Prompt where this removes modal nesting without losing export/copy functionality.

Scrapbook intensity: low-medium.

---

# Pending reference decisions

These surfaces remain governed by the UI/UX contract and current functional design until a dedicated reference is approved:

## Knowledge

Server reference folder; semantic source labels; generated empty-state art allowed. Do not invent source types that the current data model cannot distinguish.

## Interactions

Default should communicate active social activities/sessions and participant/target/status clearly. Graphs are secondary, not default.

## Conversation Intelligence

Scoped analysis surface for Topic/Thread/Entity/Intent/Continuity/Confidence and learned state. Dense analytical data stays low-decoration.

## Toolbox

Research desk grouping. Behavior Notebook remains primary; Provider Calls and Runtime Raw are Technical Evidence.

## Provider Calls

Technical request receipts; compact provider/model/latency/token/status information when the API provides it; payload expandable.

## Runtime Raw

Developer appendix. Minimal scrapbook treatment.

## Tool Calling

Experiment bench: tool list -> test sheet -> result/evidence. Functional icons stay deterministic.

## Schedules

Calendar/reminder notebook; Today/Tomorrow/Later when volume permits; actual scheduler states remain authoritative.

## Settings

Back pages/private creator pocket. Split into PageFlags only when content density justifies it.

## Admin Runtime Settings

Clipped technical configuration sheet; prioritize clarity over decoration.

## Echo Masque Lab

Separate experimental notebook; stronger stamp/illustration language allowed without weakening evaluator clarity.

## Matrix

Dense comparison sheet; paper + restrained marker/annotation only.

## Auth / Login

Studio pass/notebook entry; generated illustration is appropriate if it contains no required UI text.

---

# Implementation order from this plan

1. **Deployment Workspace** — next focused renovation.
2. Dashboard composition/data wiring to approved reference.
3. Character Archive + Character File route/composition.
4. Character Creator full-page composition.
5. Test Room composition refinement.
6. Server Notebook subpages (Knowledge / Interactions / Intelligence) as they receive approved references or clear usability requirements.
7. Remaining technical/account surfaces incrementally.

Behavior Notebook is intentionally not a priority redesign at this time.

---

# Definition of done for an approved-reference page

A page is not "done" merely because it uses cream colors, paper cards, or tape.

A renovation is complete only when:

- the approved information hierarchy is visibly present;
- the major composition matches the approved reference;
- primary/secondary actions match the page role;
- real API/types drive all displayed operational data;
- unavailable/generated-only data is not fabricated;
- shared UI/domain components are used where applicable;
- keyboard/focus/responsive behavior remains usable;
- overlay hierarchy remains correct;
- typecheck/tests/build pass;
- `/dev/ui` is updated if reusable components/variants are added;
- this plan/status is updated if implementation materially deviates from the approved reference.

# Branch safety

UI renovation must remain compatible with parallel feature development:

- avoid rewriting backend/runtime behavior solely for appearance;
- isolate data-contract additions from visual migration when they are substantial;
- do not make broad shared-component API breaks in feature PRs;
- keep feature pages -> shared/domain components -> ui primitives -> tokens dependency direction;
- generated reference assets live under `docs/ui-references/` and are documentation inputs, not runtime assets unless separately promoted.
