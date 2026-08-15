# Character Relay UI/UX Contract

Status: foundation contract. New UI should follow this document. Existing screens are grandfathered and may migrate incrementally.

## 1. Visual identity

Character Relay is a personal anime scrapbook workspace, not a corporate dashboard. The interface should feel like a notebook used to write, attach, sort, annotate, and revisit character-related material.

The scrapbook language must remain obvious without reducing readability, accessibility, or information hierarchy.

Core principles:

- Functional content stays aligned, legible, and predictable.
- Scrapbook decoration supports the interaction metaphor; it must not become visual noise.
- Character identity provides the strongest anime presence. Paper, tabs, notes, stamps, tape, and annotations provide the scrapbook frame.
- Dense technical views use the same tokens but less decoration.
- Discord-native surfaces are outside this visual contract; Character Relay does not attempt to re-skin Discord's native chat UI.

## 2. Interaction metaphors

Every meaningful Character Relay web interaction SHOULD map to one of these physical notebook actions:

| Product action | Scrapbook metaphor | Typical UI |
| --- | --- | --- |
| Enter or edit text | Write | Input, Textarea, inline StickyNote editing |
| Add content | Stick | StickyNote, PaperCard, chip, attachment |
| Navigate or switch a section | Flip / select a flag | PageFlag, PaperTab |
| Change an existing value | Rewrite / replace | Select, editable note, setting control |
| Organize content | Rearrange | sortable notes/cards where ordering is meaningful |
| Show a state/result | Annotate / stamp | Annotation, StickyLabel, Stamp |
| Reveal supporting content | Pull out a side page | Drawer / expandable paper section |

Micro-interactions may reinforce these metaphors with short lift, settle, slide, or paper-placement motion. They MUST NOT delay the task or hide state changes.

## 3. Component boundary

Feature code SHOULD consume shared UI primitives instead of inventing one-off controls.

For new feature work:

- Do not directly style native `input`, `textarea`, `select`, `button`, checkbox, radio, or switch controls when a shared primitive exists.
- Native elements are allowed inside the shared primitive implementation. Accessibility and browser semantics remain important.
- Do not copy a shared component's CSS into a feature stylesheet to make a local variant.
- Add a supported variant to the shared component when the variation is reusable.
- Business/domain components may compose primitives but MUST NOT push business-specific behavior down into base primitives.

This PR is additive. Existing native controls and `NotebookUI.tsx` are not force-migrated and no hard lint rule is introduced yet.

Dependency direction:

```text
feature UI
  -> Character Relay shared components
    -> scrapbook components
      -> base primitives
        -> design tokens
```

Base primitives MUST NOT import feature code.

## 4. Semantic scrapbook objects

### PaperCard

Use for persistent, structured information: characters, providers, model configurations, tool configurations, saved profiles.

PaperCard should look stable and intentionally filed. Rotation should be zero or nearly zero.

### StickyNote

Use for temporary, editable, supplementary, or attached information: current topic, temporary role, reminder, AI observation, user note, runtime hint, pinned context.

StickyNote may use a small paper tilt and a subtle lift-on-hover. Text itself remains upright and easy to scan.

### PageFlag / IndexTab

Use the arrow/page-index sticker language for navigation, classification, section switching, and position marking. This is a first-class navigation primitive, not decorative clip art.

Typical uses: General, Model, Memory, Tools, Media, Runtime, Inspector.

The active flag should appear slightly more exposed than inactive flags through position, shadow, and/or saturation. Color alone MUST NOT be the only active-state cue.

### StickyLabel

Use for compact capability/category metadata such as Vision, Memory, Tool, Link, Image, Active.

### Stamp

Use for a committed result or system status such as Saved, OOC, Inspected, Topic Matched. Stamps are stronger than normal labels and should be used sparingly.

### Annotation

Use for secondary notes, explanations, timestamps, or generated-by context. Annotation text must never replace a required label.

### Tape / Clip / Pin

These are decorative attachment primitives. They MUST NOT be the only affordance for a control, status, warning, or relationship that users need to understand.

## 5. Base controls

The shared foundation should cover at minimum:

- Button and IconButton
- Input and Textarea
- Select
- Checkbox, Radio, Switch
- FormField
- Tooltip and Popover
- Dialog and Drawer
- Toast
- Spinner and Skeleton
- Divider

Control behavior stays conventional even when the surface looks like paper or stationery. Focus, hover, active, disabled, read-only, loading, and error states must remain visually distinct.

## 6. Color and material

Use low-saturation stationery colors rather than fluorescent office-marker colors.

Recommended families:

- warm paper / cream
- lavender
- sakura rose
- soft peach
- butter yellow
- sage / mint
- mist blue
- muted red for destructive/error states

Large surfaces should remain neutral. Accent colors are primarily for flags, notes, labels, identity marks, and state feedback.

Paper texture may be simulated with subtle CSS gradients or image assets. Texture must not reduce text contrast.

## 7. Decoration intensity

Scrapbook intensity is intentionally uneven:

- High: PageFlags, CharacterCard, StickyNote, empty states, section covers.
- Medium: buttons, inputs, drawers, dialogs, badges/labels.
- Low: dense settings rows, logs, traces, judge metrics, structured inspector data.

Rules:

- Decorative objects do not participate in critical layout measurement.
- A card or note SHOULD have at most one dominant decorative attachment treatment at a time (for example tape OR clip OR pin).
- Do not scatter doodles into high-density data views.
- Avoid random rotation on controls, form fields, tables, logs, and long text blocks.

## 8. Image generation vs SVG/CSS contract

Character Relay explicitly permits generated raster imagery where it produces a better scrapbook/anime result than deterministic SVG or CSS.

### Generated images MAY be used when

- the asset depends on organic paper texture, imperfect edges, hand-drawn marks, stationery collage, tape/paper illustration, or anime character artwork;
- a decorative illustration or empty-state artwork benefits from a hand-made appearance;
- reproducing the desired visual in SVG would create unnecessary complexity or a visibly sterile result;
- the generated asset is decorative or illustrative and can be safely replaced without changing product semantics.

There is **no requirement to use SVG merely because the asset is part of the UI**.

### SVG/CSS SHOULD remain preferred when

- the asset is a functional icon or state-bearing symbol;
- crisp deterministic geometry and scaling are important;
- the visual is a simple shape, border, tab silhouette, divider, focus ring, or control affordance;
- the asset must adapt precisely to theme/state through code;
- a simple CSS/SVG solution is smaller, clearer, and easier to maintain.

### Generated images MUST NOT

- replace accessible text, form labels, required instructions, or critical state indicators;
- bake translatable/localized UI copy into an image when that copy needs to change by locale;
- be the only source of information for an error, warning, selected state, or control affordance;
- be generated just to approximate a trivial rectangle, arrow, dot, checkbox, or other basic geometry that CSS/SVG handles cleanly.

For generated or raster assets:

- meaningful imagery requires useful `alt` text;
- purely decorative imagery should use empty alt text or `aria-hidden` as appropriate;
- source prompts do not need to be coupled to runtime UI behavior;
- store optimized production assets in the repository or approved asset storage rather than depending on a generation call at render time.

Decision rule: **use code for function and deterministic geometry; use generated imagery when the value comes from illustration, texture, or intentionally organic visual character.**

## 9. Accessibility and motion

- All interactive elements require visible keyboard focus.
- PageFlag/PaperTab navigation must expose selected state through semantics such as `aria-selected` where appropriate.
- Switches use checkbox semantics with `role="switch"` and `aria-checked`/checked state.
- Color is never the sole carrier of status.
- Decorative images and stationery ornaments must not pollute the accessibility tree.
- Respect `prefers-reduced-motion`; scrapbook lift/settle effects become effectively static.
- Keep touch/click targets practical even when the visible sticker is compact.

## 10. Rollout policy

1. Build tokens and shared components additively.
2. New feature work should prefer the shared system.
3. Migrate existing screens when those screens are already being touched or through focused migration PRs.
4. Introduce lint enforcement only after shared coverage is broad enough; start with warnings or scoped checks before hard CI errors.
5. Avoid broad UI rewrites in feature branches that are simultaneously changing business logic.
