# Character Relay UI Phase 2 — Character Workflow Review

Status: Draft PR visual/interaction review checklist.

This checklist is intentionally separate from runtime correctness. Phase 2 must not change trial semantics, Smart Participation authority, Provider behavior, or stored evidence meaning.

## Test Room

- [x] Live transcript remains the dominant surface.
- [x] Setup controls read as a compact experiment setup page.
- [x] Observation/integrity/persona information reads as attached notes.
- [x] Judge and comparison outcomes use shared Stamp language.
- [x] Loading/empty/error states use shared components.
- [x] Transcript decoration remains lower than the observation margin.
- [x] Mobile layout keeps transcript before observation notes.
- [ ] Replace remaining legacy setup controls opportunistically when those controls are next edited.

## Behavior Notebook

- [x] Narrative summary appears before technical trace detail.
- [x] Behavior / Flow / State / Raw use PaperTab semantics.
- [x] Search, filter, status, empty, loading, and error states use shared UI.
- [x] Summary/evidence use real StickyNote components.
- [x] State, raw trace, observation margin, and Provider evidence use InspectorSection.
- [x] Provider detail reads as a technical receipt/side insert.
- [x] Dense evidence keeps low scrapbook decoration intensity.
- [ ] Consider promoting any repeated Runtime-specific receipt pattern into a shared domain component after a second production use appears.

## Prompt Inspector

- [x] Raw and Compiled Prompt use PaperTab navigation.
- [x] Source vs runtime state uses Stamp / StickyLabel.
- [x] Loading/error/copy/export controls use shared UI.
- [x] Escape closes the inspector.
- [x] Prompt source remains readable and monospace.
- [x] No generated illustration is used because it would not improve the task.

## Shared component library

- [x] Feedback primitives cover StatusIndicator, InspectorSection, EmptyState, SearchField, Tooltip, Popover, Spinner, Skeleton, Divider, and Toast.
- [x] Character Relay-aware shared layer exists separately from business-agnostic `ui/` primitives.
- [x] Shared domain compositions cover ProviderSelect, ModelSelect, ApiKeyField, TopicNote, TemporaryRoleNote, and ParticipantCard.
- [x] `/dev/ui` shows both primitive and domain component families.
- [x] Generated-image-safe illustration slots remain optional and non-semantic.

## Accessibility / motion

- [x] Shared interactive components expose keyboard focus.
- [x] PaperTab exposes tab semantics and selected state.
- [x] Status uses text/shape in addition to color.
- [x] Reduced-motion styles disable decorative lift/rotation where applicable.
- [x] Generated images are not required for any state or action in this phase.

## Deferred structural work

These are intentionally not blockers for the Phase 2 character-workflow visual slice:

1. Character Creator controlled form state and true page-by-page navigation.
2. Character Shelf action consolidation into `Test Character` + `Open File` hierarchy.
3. Deployment Server Passport and connection-management Drawer.
4. Knowledge / Interactions / Conversation Intelligence structural migration.
5. Production generated illustration pass for Dashboard, Auth, Knowledge empty state, and Echo Masque where useful.
