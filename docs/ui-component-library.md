# Character Relay Scrapbook Component Library

This document describes the shared UI vocabulary for Character Relay's web interface. It complements `docs/ui-ux-contract.md`.

## Layering

```text
design tokens
  -> base controls
    -> scrapbook objects
      -> Character Relay domain components
```

Implementation is split intentionally:

- `web/src/components/ui/` contains business-agnostic primitives and scrapbook objects;
- `web/src/components/shared/` contains reusable Character Relay-aware compositions;
- feature pages compose the shared layers instead of copying their CSS or behavior.

## Base controls

### Button

Variants: `primary`, `secondary`, `ghost`, `danger`.

Visual metaphor: a small action label or paper sticker. Primary actions receive the clearest stationery accent; ghost actions stay quiet until hover/focus.

### IconButton

Compact page-edge tool for actions such as close, edit, refresh, more, or remove. Keep the hit target usable even if the visible mark is small.

### FunctionalIcon

Deterministic inline-SVG functional icon primitive. Use for navigation, search, close, refresh, settings, runtime/tool identifiers, and other state/action geometry where a generated image would be inappropriate.

The current icon set includes:

- home;
- characters;
- deployment;
- toolbox;
- settings;
- overview;
- behavior;
- provider;
- runtime;
- tools;
- schedule;
- chevron;
- close;
- search;
- refresh.

This component directly implements the contract rule: **functional geometry stays code/SVG; organic illustration may use generated raster art.**

### Input

A notebook writing field. Warm paper surface, subtle border, clear focus ring, conventional text editing behavior.

### Textarea

A larger writing area for personality, prompts, descriptions, and notes. Supports the same invalid/disabled/focus language as Input.

### Select

A paper-field selector. The native select remains semantic; the wrapper supplies the scrapbook surface and chevron treatment.

### Checkbox / Radio / Switch

Conventional form semantics with stationery styling. These controls represent marks made in the notebook, not game-like toggles.

### FormField

Standardizes label, hint, error message, and control spacing so feature pages do not rebuild field layouts independently.

## Scrapbook objects

### PaperCard

Persistent, structured content. Use for characters, saved provider/model profiles, tool configurations, templates, or other filed information.

Properties:

- stable paper surface;
- subtle layered-sheet edge;
- optional interactive lift;
- no arbitrary large rotation.

### StickyNote

Temporary, editable, supplementary, or session-scoped information.

Variants:

- `note`
- `topic`
- `reminder`
- `character`
- `temporary`
- `warning`
- `system`

Typical uses: current topic, temporary role, reminder, AI observation, user note, pinned runtime context, active interaction session.

Sizes: `sm`, `md`, `lg`.

### PageFlag

First-class navigation/index sticker based on physical arrow/page flags.

Tones:

- rose
- peach
- yellow
- mint
- blue
- lavender

Use for section navigation such as Identity / Persona / Voice / Boundaries / Memory / Runtime / Review. Active state uses position and shadow as well as color.

### PaperTab

Horizontal notebook-tab primitive for smaller peer views such as Raw / Compiled Prompt or Behavior / Flow / State / Raw.

### StickyLabel

Compact metadata sticker for capabilities and lightweight states.

Suggested variants include neutral, vision, memory, tool, link, image, success, warning, and danger.

### Stamp

Strong result/status mark for Saved, OOC, Inspected, Topic Matched, PASS/FAIL/REVIEW, and similar committed decisions.

### Annotation

Secondary handwritten-note treatment for generated-by information, timestamps, small explanatory cues, or side comments.

## Shared feedback and technical UI

Reusable feedback and technical-inspection primitives in `web/src/components/ui/FeedbackUI.tsx` include:

- `StatusIndicator` — compact live/ready/warning/failure status with optional pulse;
- `InspectorSection` — lower-decoration technical paper section for dense evidence;
- `EmptyState` — centered empty-state layout with an illustration slot that may use generated raster art;
- `SearchField` — shared paper search input using the deterministic SVG search icon;
- `Tooltip` and `Popover` — supporting explanation/detail surfaces;
- `Spinner` and `Skeleton` — loading states that remain visually consistent with the paper system;
- `Divider` — semantic paper divider;
- `Toast` — small pinned-note feedback surface for success/warning/error state.

These components remain business-agnostic and live in the `ui/` layer.

## Character Relay shared/domain components

Reusable product-aware compositions live in `web/src/components/shared/`.

### ProviderSelect

`FormField + Select` composition for choosing a configured provider. Provider knowledge belongs here rather than in the base Select primitive.

### ModelSelect

Model selector that can expose compact model metadata while retaining standard select behavior.

### ApiKeyField

`FormField + Input + Button` composition for credential visibility and status. The base Input does not know what an API credential is.

### TopicNote

StickyNote composition for current conversation topic, confidence, participants, optional topic state, and supplementary topic summary content.

### TemporaryRoleNote

Small removable/temporary role note. Changing a temporary social role should feel like replacing a note rather than editing permanent character identity.

### ParticipantCard

`PaperCard + Avatar + StickyLabel + attached StickyNote` composition for stable participant identity plus runtime state.

## Existing shared compositions

### CharacterChip

Compact participant/character selection item. May show avatar, name, and optional remove action.

### SettingsRow

Consistent title + description + control layout for switch/checkbox/select settings.

### PaperDrawer / PaperModal

Existing `NotebookUI.tsx` overlays remain supported bridge components and are re-exported from `components/ui`. Current production migrations use PaperDrawer for Character File, Character Creator, Interaction Template, Interaction Apply, Connection configuration, and other side-page workflows.

## Production adoption

The component system is no longer showcase-only. Current production use includes:

- **Global Shell** — FunctionalIcon + StickyLabel section marker;
- **Dashboard** — Button + StickyNote hierarchy;
- **Character Shelf** — SearchField / Select / Button / EmptyState / Toast / Character File PaperDrawer;
- **Character Creator** — PageFlag, FormField, Input, Textarea, Select, ProviderSelect, ApiKeyField, StickyNote, PaperTab, Toast, Spinner;
- **Test Room** — Button, StatusIndicator, StickyLabel, StickyNote, Stamp, EmptyState, Toast;
- **Prompt Inspector** — PaperTab, Stamp, StickyLabel, Button, Select, Spinner, Toast;
- **Behavior Notebook** — PaperTab, SearchField, StatusIndicator, StickyNote, Stamp, InspectorSection, EmptyState, Spinner, Toast;
- **Knowledge** — shared form controls, status, folder labels, retrieval empty/error/loading states;
- **Interactions** — PaperCard templates, StickyNote session journal, PaperTab navigation, PaperDrawer editors, shared controls/status;
- **Conversation Intelligence** — InspectorSection, TopicNote, StickyNote, Select, EmptyState, Spinner, Toast;
- **Schedules** — StickyNote reminder records, StatusIndicator, Select, Switch, Button, EmptyState, Spinner, Toast;
- **Auth** — PaperCard, PaperTab, FormField, Input, Button, Spinner, StickyLabel, StickyNote, Toast;
- **Toolbox** — FunctionalIcon hierarchy with Technical Evidence separated from Behavior Notebook.

Dense technical pages such as Provider Calls and Runtime Raw intentionally retain lower decoration intensity and inherit shared tokens rather than being converted into decorative note grids.

## Living showcase

`/dev/ui` is the Super Admin-only living component showcase. It runs through the normal
Session bootstrap and verifies the server-provided `is_super_admin` signal before the
catalog chunk is loaded. The Administration page is its only in-product entry point.

The inventory is derived from module exports instead of a handwritten total. It currently
contains **48 reusable components**:

- 36 business-agnostic `components/ui` exports, including the two Notebook overlay bridges;
- 6 Character Relay-aware `components/shared` compositions;
- 5 production-reused Notebook controls not yet migrated into the canonical barrel;
- 1 shared Pagination component.

The first two groups are the 42-component formal library. The final six remain visible as
shared utilities so migration debt is explicit instead of disappearing from the count.
Feature-only page components are deliberately excluded.

The showcase covers:

- actions and status;
- form controls;
- PageFlags / PaperTabs;
- StickyNotes / labels / stamps / annotations;
- technical inspector patterns;
- tooltip / popover;
- spinner / skeleton / toast;
- illustration-safe empty states;
- avatar and settings rows;
- Provider / Model / API Key compositions;
- TopicNote / TemporaryRoleNote / ParticipantCard;
- Notebook compatibility controls and shared Pagination;
- IconButton / CharacterChip / PaperDrawer / PaperModal;
- every current FunctionalIcon name.

Generated illustration slots shown in the showcase are examples only. Production artwork must follow the image-generation contract in `docs/ui-ux-contract.md`.

## Styling rules

- Shared foundation classes use the `cr-` prefix to avoid feature stylesheet collisions.
- Theme values come from `tokens.css` custom properties.
- Large surfaces stay warm-neutral; scrapbook colors are accents.
- Paper texture is subtle and cannot reduce text contrast.
- Sticky-note tilt is slight and never applied to long structured content.
- Functional controls stay aligned even when their surface suggests paper/stationery.
- Decorations never become required controls.
- Dense developer/trace views intentionally use lower decoration intensity than character-facing pages.
- Page-specific CSS owns only layout/composition genuinely unique to that feature; reusable behavior belongs in a shared component.
- `stabilization-hotfix.css` is the final compatibility layer: import it once from `web/src/main.tsx`, after the page styles. Feature components must not import it because module-order deduplication would move its rules ahead of later page CSS and make the cascade route-dependent.

## Imports

Business-agnostic primitives:

```ts
import {
  Button,
  FunctionalIcon,
  Input,
  StickyNote,
  PageFlag,
  PaperCard
} from "./components/ui";
```

Character Relay-aware shared compositions:

```ts
import {
  ApiKeyField,
  ModelSelect,
  ParticipantCard,
  ProviderSelect,
  TopicNote
} from "./components/shared";
```

New feature work should use these shared layers. Grandfathered native controls inside dense legacy technical pages may migrate opportunistically when the page is next edited; they are not a reason to rewrite Runtime/business logic solely for style.
