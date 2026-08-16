# Character Relay — Scrapbook Page Migration Plan

Status: accepted design direction

This document translates the UI/UX contract into page-level decisions. The goal is not to make every screen look like the same paper card. Each area should feel like a different part of the same anime research notebook while preserving dense technical readability where needed.

## Global rule

Character Relay Web UI is a personal anime scrapbook workspace, not a conventional enterprise admin console.

Each meaningful action should map to one of the contract interaction metaphors:

- Write — enter or edit information.
- Stick — add a character, note, reminder, attachment, or other new item.
- Flip — move between notebook sections or indexed pages.
- Rewrite / Replace — modify an existing selection or configuration.
- Rearrange — organize information that is genuinely spatial or sortable.
- Annotate / Stamp — display state, evidence, warnings, decisions, or observations.

Functional behavior stays conventional and accessible. Scrapbook styling is a visual and micro-interaction layer, not a reason to make controls ambiguous.

## Generated imagery rule

Generated raster artwork is allowed when it is better than SVG/CSS for organic or illustrative material such as:

- dashboard scrapbook illustrations;
- anime character or mascot artwork;
- paper texture with natural irregularity;
- collage decoration;
- hand-drawn stationery elements;
- empty-state illustrations;
- optional decorative stickers.

Do not imitate these assets with complicated SVG merely to avoid image generation.

SVG/CSS remains preferred for functional icons, state-bearing shapes, simple geometry, deterministic controls, focus affordances, and elements whose exact scaling matters.

Generated imagery must never contain required UI text, replace accessible labels, encode the only copy of a state, or become necessary to understand an action.

---

# Page decisions

## 1. Global Shell

Visual role: the notebook frame / research workspace.

Keep the existing primary navigation structure because it is efficient. Do not turn the entire top bar into decorative page flags.

Adjustments:

- keep the Character Relay wordmark;
- use consistent functional icons instead of decorative Unicode glyphs over time;
- show a small section marker so the current notebook area is obvious;
- active navigation should feel like a selected notebook index without losing standard navigation affordance;
- keep decoration outside layout flow;
- let individual pages carry stronger scrapbook identity than the global shell.

Scrapbook intensity: medium.

## 2. Dashboard

Visual role: notebook cover + today's research desk.

The dashboard is one of the strongest identity surfaces and may use generated imagery.

Adjustments:

- retain the current research-studio headline and workflow concept;
- make Characters / current character work the strongest visual destination;
- make Deployments and Behavior Observer secondary;
- make Settings visually quieter;
- keep the Studio Note as a real StickyNote-style object;
- reserve an optional illustration area for generated anime scrapbook artwork without embedded text;
- treat navigation cards as notebook destinations rather than generic SaaS KPI cards.

Scrapbook intensity: high.

## 3. Characters / Character Shelf

Visual role: character archive / scrapbook shelf.

Adjustments:

- character portrait is the strongest element on every card;
- reduce visible action competition;
- primary actions should become `Test Character` and `Open File`;
- Prompt, Semantic Profile, Deploy, portrait management, and other actions should move into the character file or a compact secondary action area;
- filters stay in the page margin, following the existing “find a character, not a spreadsheet” direction;
- tags use StickyLabel semantics;
- character cards remain PaperCards rather than StickyNotes because they are durable records;
- image upload, future image generation, and no-portrait state must all remain valid.

Scrapbook intensity: high.

## 4. Character Creator / Editor

Visual role: actively written character setting notebook.

This is a priority structural migration because the current editor is still a long form.

Target section model:

1. Identity
2. Persona / Personality
3. Voice / Prompt
4. Boundaries
5. Memory
6. Runtime
7. Review

Adjustments:

- use PageFlag / IndexTab navigation;
- preserve one underlying form state across pages;
- avoid unmounting uncontrolled fields in a way that loses FormData or browser validation state;
- AI Draft becomes a StickyNote-like assistant entry instead of dominating the top of the form;
- after AI Draft, changed fields should be visibly annotated for review;
- generated drafts never auto-save;
- API Key and Provider settings are not modified by AI Draft;
- final save action should feel like committing the character page rather than submitting a generic web form.

Migration note: true page-by-page editing should be introduced only after field state is controlled or validation is explicitly coordinated. Until then, PageFlags may act as safe section indexes rather than hiding required uncontrolled fields.

Scrapbook intensity: high.

## 5. Test Room

Visual role: live character experiment.

Target layout:

- main conversation area around two thirds of the width;
- observation margin around one third;
- technical detail stays secondary by default.

Observation margin candidates:

- Current Topic StickyNote;
- participation state;
- media seen / understood;
- tool use;
- memory or retrieval event;
- judge / OOC signal;
- latest interesting runtime event.

Default UX should explain what happened in human-readable form first. Raw traces expand on demand.

Phase 2 implementation status:

- live transcript is now the dominant paper sheet;
- setup controls are visually grouped as a compact experiment setup page;
- observation/integrity/persona/report information is treated as attached notes rather than an equal third dashboard column;
- visible state/action surfaces use shared Button, StatusIndicator, StickyLabel, StickyNote, Stamp, EmptyState, and Toast primitives;
- transcript readability remains intentionally cleaner than the observation margin;
- trial/runtime behavior remains unchanged.

Scrapbook intensity: medium-high.

## 6. Prompt Inspector

Visual role: prompt manuscript pulled from the character file.

Suggested PaperTabs:

- System Prompt
- Runtime Injections
- Final Composed Prompt

The current runtime only exposes Raw Prompt and Compiled Character Prompt, so Phase 2 does not invent unavailable layers. Raw / Compiled use PaperTab navigation until the data model provides additional authoritative layers.

Phase 2 implementation status:

- Raw and Compiled layers use shared PaperTab navigation;
- source/runtime distinction uses Stamp and StickyLabel;
- copy/export/loading/error states use shared UI primitives;
- Escape-to-close is supported;
- generated imagery remains unnecessary here.

Prioritize typography and readability. Generated imagery is unnecessary here.

Scrapbook intensity: low-medium.

## 7. Deployments

Visual role: Server Notebook / field deployment manual.

Target structure:

- top Server Passport showing selected server, connection state, channel count, character count, knowledge count, and last sync;
- PageFlags for Characters, Knowledge, Interactions, Intelligence;
- platform connection management moves out of the permanent main layout and into a Drawer;
- deployment configuration remains accessible but no longer competes with the daily server view;
- Discord itself remains native and is not reskinned by Character Relay.

Scrapbook intensity: high for navigation, medium for configuration.

## 8. Deployment → Characters

Visual role: who currently lives in this server.

Use character-oriented deployment rows/cards showing:

- portrait and name;
- participation mode;
- channel scope;
- identity;
- tools;
- status.

Open the detailed deployment sheet only when needed.

Scrapbook intensity: medium.

## 9. Knowledge

Visual role: server reference folder.

Knowledge source types can use semantic StickyLabels:

- document;
- note;
- link;
- conversation-derived knowledge.

Color represents source semantics, not random decoration. Empty state may use generated illustration.

Scrapbook intensity: medium-high.

## 10. Interactions

Visual role: interaction journal.

Default view should answer “who interacted with whom, about what, and what changed?” rather than defaulting to a graph.

A Relationship Graph may be added later as a secondary view if graph-based runtime work becomes useful.

Scrapbook intensity: medium.

## 11. Conversation Intelligence

Visual role: research analysis page.

Key information includes Topic, Thread, Entity, Intent, Continuity, and Confidence.

Use annotation and light note metaphors, but do not turn dense analytical data into decorative paper fragments.

Scrapbook intensity: low-medium.

## 12. Toolbox / Behavior Observer

Visual role: research desk.

Keep Observe and Tools as the main grouping.

Behavior Notebook is the primary research surface. Provider Calls and Runtime Raw should be visually grouped as Technical Evidence rather than presented as equally important user destinations.

Scrapbook intensity: medium.

## 13. Behavior Notebook

Visual role: readable experiment record.

Required information hierarchy:

1. narrative summary of what the character turn did;
2. important observations and decisions;
3. expandable evidence;
4. raw traces last.

Example narrative:

- Ann saw the image;
- interpreted it as food;
- current topic stayed dinner;
- decided to reply;
- no tool was used;
- response generated successfully.

Expandable evidence may include Media Understanding, Topic Judge, Participant Runtime, Provider Trace, Tool Calls, and Prompt.

Principle: Narrative first → Trace second.

Phase 2 implementation status:

- Behavior / Flow / State / Raw now use the shared PaperTab language;
- turn summaries and evidence use real StickyNote components;
- search/filter/status/error/loading surfaces are migrating to SearchField, Button, StatusIndicator, Toast, EmptyState, and Spinner;
- observation, state, raw trace, and provider evidence use InspectorSection so dense technical surfaces share the same low-decoration foundation;
- provider result detail reads as a technical receipt/side insert rather than a separate monitoring product;
- runtime/business logic and evidence semantics remain unchanged.

Scrapbook intensity: medium.

## 14. Provider Calls

Visual role: technical request receipts / evidence slips.

Compact request items may show Provider, Model, Latency, Tokens, Cost, Cache, and Status. Payload and raw response remain expandable.

Scrapbook intensity: low-medium.

## 15. Runtime Raw

Visual role: developer appendix.

Do not heavily scrapbook this page. Standardize typography, buttons, tabs, state colors, and paper container only.

Scrapbook intensity: low.

## 16. Tool Calling

Visual role: experiment bench.

Suggested structure:

- tool list;
- test sheet;
- result / evidence area.

Functional icons stay SVG/CSS. Optional decorative stickers may use generated imagery.

Scrapbook intensity: medium.

## 17. Schedules

Visual role: calendar + reminder notes.

Prefer Today / Tomorrow / Later groupings with StickyNote-style reminders instead of a dense data table when scale allows.

Scrapbook intensity: medium-high.

## 18. Settings

Visual role: back pages / private creator pocket.

Near-term structure can remain compact. When settings grow, split into PageFlags such as:

- Account
- Providers
- Runtime
- Security
- Preferences

Avoid premature page splitting until content volume justifies it.

Scrapbook intensity: medium.

## 19. Admin Runtime Settings

Visual role: clipped system configuration sheet.

Keep technical readability high. Provider, Judge, Adaptive, Utility Gateway, and similar groups may become PaperTabs when necessary.

Scrapbook intensity: low-medium.

## 20. Echo Masque Lab

Visual role: separate experimental notebook.

This area may use stronger generated artwork and stamp language such as PASS, OOC, DRIFT, REVIEW while preserving evaluative clarity.

Scrapbook intensity: high.

## 21. Matrix

Visual role: experiment comparison sheet.

Keep the matrix dense and readable. Use paper surface, marker-style highlight, and annotation only.

Scrapbook intensity: low-medium.

## 22. Auth / Login

Visual role: studio pass / notebook entry page.

Generated illustration is recommended here because it can communicate project identity before the user reaches the workspace. Illustration should contain no required UI copy.

Scrapbook intensity: high.

---

# Delivery phases

## Phase 1 — visual hierarchy and safe adoption

Status: implemented on `main` through the initial scrapbook foundation/page pass.

- Global Shell
- Dashboard
- Character Shelf visual hierarchy
- Character Creator visual treatment
- shared component adoption where it does not change business behavior
- no destructive layout migration

## Phase 2 — character workflow

Status: in progress in the Phase 2 character-workflow PR.

Implemented / actively migrated:

- Test Room presentation and shared component adoption;
- Behavior Notebook narrative/trace hierarchy and shared component adoption;
- Prompt Inspector manuscript treatment;
- feedback/technical primitives;
- `/dev/ui` living component showcase;
- Character Relay shared/domain components for Provider, Model, API Key, Topic, Temporary Role, and Participant patterns.

Still structural follow-up:

- Character Creator true page navigation after form state is safe.

## Phase 3 — server workflow

- Deployment Center
- Knowledge
- Interactions
- Conversation Intelligence

## Phase 4 — technical and account surfaces

- Toolbox hierarchy
- Provider Calls
- Runtime Raw
- Tool Calling
- Schedules
- Settings
- Admin Runtime

## Phase 5 — illustration pass

Generate only the assets that materially improve identity or empty states. Do not produce generated art merely to fill space.

Candidate generated assets:

- Dashboard research-desk illustration;
- Auth studio-pass illustration;
- Knowledge empty state;
- Echo Masque Lab experiment illustration;
- optional restrained sticker set.

# Branch safety

Page migration should remain incremental and should not force unrelated feature branches to rebase around large component API changes.

Preferred dependency direction remains:

`feature pages → shared/domain components → ui primitives → tokens`

Existing feature logic should not be rewritten solely for styling. Structural refactors require their own focused PR when they materially change interaction or state handling.
