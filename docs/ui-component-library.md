# Character Relay Scrapbook Component Library

This document describes the shared UI vocabulary for Character Relay's web interface. It complements `docs/ui-ux-contract.md`.

## Layering

```text
design tokens
  -> base controls
    -> scrapbook objects
      -> Character Relay domain components
```

The first implementation lives under `web/src/components/ui/` and is intentionally additive. Existing feature pages are not migrated in this foundation PR.

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

## Character Relay compositions

These compositions can be built on top of the primitives without adding business knowledge to the base layer.

### CharacterCard

`PaperCard + Avatar + StickyLabel`

Carries persistent character identity, provider/model metadata, and capabilities.

### CharacterChip

Compact participant/character selection item. May show avatar, name, and optional remove action.

### SettingsRow

Consistent title + description + control layout for switch/checkbox/select settings.

### ProviderSelect / ModelSelect

Domain selectors built on Select. Rich model/provider metadata belongs here rather than inside the base Select primitive.

### ApiKeyField

`FormField + Input + IconButton` composition for credential visibility, validation, and clearing.

### TopicNote

StickyNote composition for current conversation topic and optional supporting metadata.

### TemporaryRoleNote

StickyNote composition attached to a character/participant context. Changing a role should feel like replacing a removable note.

### ParticipantCard

PaperCard for stable participant identity with attached small note/label for runtime state.

### InspectorSection

Dense technical paper section using the same tokens with reduced decoration. Prefer compact rows, stamps, and annotations over decorative sticky-note grids.

## Overlay and feedback components

Existing shared `PaperDrawer` and `PaperModal` in `web/src/NotebookUI.tsx` remain valid bridge components. They are re-exported from the new UI entry point so new code can use the shared namespace without forcing an immediate migration.

Future shared feedback coverage should include Popover, Tooltip, Toast, Spinner, and Skeleton. This foundation does not need to replace every existing implementation at once.

## Styling rules

- All new classes in the foundation use the `cr-` prefix to avoid feature stylesheet collisions.
- Theme values come from `tokens.css` custom properties.
- Large surfaces stay warm-neutral; scrapbook colors are accents.
- Paper texture is subtle and cannot reduce text contrast.
- Sticky-note tilt is slight and never applied to long structured content.
- Functional controls stay aligned even when their surface suggests paper/stationery.
- Decorations never become required controls.

## Adoption

New feature code should import from:

```ts
import {
  Button,
  Input,
  StickyNote,
  PageFlag,
  PaperCard
} from "./components/ui";
```

Existing screens can migrate incrementally. Do not mix UI migration with unrelated business-logic refactors unless the change is very small and conflict-safe.
