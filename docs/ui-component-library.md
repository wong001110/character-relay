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

Persistent, structured content. Use for characters, saved provider/model profiles, tool configurations, or other filed information.

Properties:

- stable paper surface;
- subtle layered-sheet edge;
- optional interactive lift;
- no arbitrary large rotation.

### StickyNote

Temporary, editable, or supplementary information.

Variants:

- `note`
- `topic`
- `reminder`
- `character`
- `temporary`
- `warning`
- `system`

Typical uses: current topic, temporary role, reminder, AI observation, user note, pinned runtime context.

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

Use for section navigation such as General / Model / Memory / Tools / Media / Runtime / Inspector. Active state uses position and shadow as well as color.

### StickyLabel

Compact metadata sticker for capabilities and lightweight states.

Suggested variants include neutral, vision, memory, tool, link, image, success, warning, and danger.

### Stamp

Strong result/status mark for Saved, OOC, Inspected, Topic Matched, and similar completed decisions.

### Annotation

Secondary handwritten-note treatment for generated-by information, timestamps, small explanatory cues, or side comments.

## Shared feedback and technical UI

Phase 2 adds reusable feedback and technical-inspection primitives in `web/src/components/ui/FeedbackUI.tsx`:

- `StatusIndicator` — compact live/ready/warning/failure status with optional pulse;
- `InspectorSection` — lower-decoration technical paper section for dense evidence;
- `EmptyState` — centered empty-state layout with an illustration slot that may use generated raster art;
- `SearchField` — shared paper search input;
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

StickyNote composition for current conversation topic, confidence, participants, and optional topic state.

### TemporaryRoleNote

Small removable/temporary role note. Changing a temporary social role should feel like replacing a note rather than editing permanent character identity.

### ParticipantCard

`PaperCard + Avatar + StickyLabel + attached StickyNote` composition for stable participant identity plus runtime state.

## Additional Character Relay compositions

The following compositions remain valid targets as more pages migrate:

### CharacterCard

`PaperCard + Avatar + StickyLabel`

Carries persistent character identity, provider/model metadata, and capabilities.

### CharacterChip

Compact participant/character selection item. May show avatar, name, and optional remove action.

### SettingsRow

Consistent title + description + control layout for switch/checkbox/select settings.

### InspectorSection

Dense technical paper section using the same tokens with reduced decoration. Prefer compact rows, stamps, and annotations over decorative sticky-note grids.

## Overlay and feedback components

Existing shared `PaperDrawer` and `PaperModal` in `web/src/NotebookUI.tsx` remain valid bridge components. They are re-exported from the new UI entry point so new code can use the shared namespace without forcing an immediate migration.

## Living showcase

`/dev/ui` is the development-only living component showcase. It should be updated whenever a reusable UI primitive or Character Relay shared composition is added.

The showcase currently covers:

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
- TopicNote / TemporaryRoleNote / ParticipantCard.

Generated illustration slots shown in the showcase are examples only. Production artwork must follow the image-generation contract in `docs/ui-ux-contract.md`.

## Styling rules

- All new classes in the foundation use the `cr-` prefix to avoid feature stylesheet collisions.
- Theme values come from `tokens.css` custom properties.
- Large surfaces stay warm-neutral; scrapbook colors are accents.
- Paper texture is subtle and cannot reduce text contrast.
- Sticky-note tilt is slight and never applied to long structured content.
- Functional controls stay aligned even when their surface suggests paper/stationery.
- Decorations never become required controls.
- Dense developer/trace views intentionally use lower decoration intensity than character-facing pages.

## Adoption

Business-agnostic primitives:

```ts
import {
  Button,
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

Existing screens can migrate incrementally. Do not mix UI migration with unrelated business-logic refactors unless the change is very small and conflict-safe.
