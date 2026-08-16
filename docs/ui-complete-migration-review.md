# Character Relay — Complete Scrapbook UI Migration Review

Status: implementation review for the final UI migration PR.

This checklist closes the page plan in `docs/ui-page-migration-plan.md`. “Complete” means the page follows the accepted visual/interaction contract without changing Runtime semantics. It does not mean every grandfathered internal native element has been deleted; dense technical controls may migrate opportunistically when next edited.

## Shared system

- [x] Design tokens cover paper/ink/accent/semantic/focus/depth/motion/typography.
- [x] Business-agnostic primitives live in `web/src/components/ui/`.
- [x] Character Relay-aware compositions live in `web/src/components/shared/`.
- [x] `/dev/ui` renders both primitive and domain component families.
- [x] Functional navigation icons use deterministic SVG rather than Unicode glyphs.
- [x] Generated imagery remains explicitly allowed for organic illustration/texture and explicitly optional.
- [x] `prefers-reduced-motion` is respected by shared and page-level scrapbook motion.
- [x] Discord-native chat is outside the web skinning contract.

## Page closure

### 1. Global Shell
- [x] Standard primary navigation retained.
- [x] Notebook section marker added.
- [x] Functional top-level icons migrated to shared SVG icon primitive.
- [x] Scrapbook identity stays lighter than individual pages.

### 2. Dashboard
- [x] Character work is visually dominant.
- [x] Deployment / Observer are secondary destinations.
- [x] Settings is visually quieter.
- [x] Studio Note uses a real StickyNote.
- [x] Generated hero artwork remains optional rather than required for comprehension.

### 3. Character Shelf
- [x] Portrait and identity dominate cards.
- [x] Card action competition reduced to Test Character / Open File / Deploy.
- [x] Prompt / Semantic / Edit / portrait management moved into Character File drawer.
- [x] Search and filters use shared controls.
- [x] Empty/error/feedback states use shared UI.

### 4. Character Creator
- [x] Controlled field state replaces the unsafe long uncontrolled-form navigation model.
- [x] True PageFlag pages: Identity / Persona / Voice / Boundaries / Memory / Runtime / Review.
- [x] Page validation directs users to the page that needs attention.
- [x] AI Draft never auto-saves.
- [x] AI Draft does not modify Provider or API credentials.
- [x] Review page is the only commit surface.

### 5. Test Room
- [x] Live transcript remains dominant.
- [x] Setup is a compact experiment sheet.
- [x] Observation rail behaves like attached research notes.
- [x] Shared status/empty/error/stamp/note components are used.
- [x] Trial/Judge/Runtime semantics remain unchanged.

### 6. Prompt Inspector
- [x] Raw / Compiled use PaperTab.
- [x] Source/runtime roles use Stamp and StickyLabel.
- [x] Shared loading/error/copy/export controls are used.
- [x] Escape-to-close supported.
- [x] No unnecessary generated illustration added.

### 7. Deployments
- [x] Selected server reads visually as a Server Passport.
- [x] Characters / Knowledge / Interactions / Intelligence remain the primary Server Notebook pages.
- [x] Connections are visually demoted below the daily server workspace.
- [x] Connection and Deployment editing stay in Drawer surfaces.
- [x] Discord-native UI is not imitated or re-skinned.

### 8. Deployment → Characters
- [x] Existing character-oriented deployment cards remain the primary content.
- [x] Detailed deployment configuration stays in a drawer/sheet.
- [x] Main server notebook hierarchy is preserved.

### 9. Knowledge
- [x] Knowledge Base reads as a folder; Document is the actual RAG source.
- [x] Create/filter/retrieval controls use shared controls.
- [x] Scope and enabled state use label/status semantics.
- [x] Empty/loading/error states use shared UI.
- [x] Retrieval results remain dense/readable and do not invoke the character LLM.

### 10. Interactions
- [x] Templates are persistent filed rule cards.
- [x] Sessions are presented as an Interaction Journal.
- [x] Templates / Sessions use PaperTab navigation.
- [x] Session state uses shared status indicators.
- [x] Template/apply editors use PaperDrawer + shared form controls.

### 11. Conversation Intelligence
- [x] Character Card remains clearly authoritative.
- [x] Learned State stays a lower-decoration derived evidence view.
- [x] Current Topic uses TopicNote.
- [x] Character/Channel selectors, empty/loading/error states use shared components.
- [x] Topic timeline remains readable technical evidence.

### 12. Toolbox / Behavior Observer
- [x] Behavior Notebook is the primary research surface.
- [x] Provider Calls and Runtime Raw are grouped under Technical Evidence.
- [x] Tool Calling and Schedules remain separate tools.
- [x] Functional navigation icons use shared SVG.

### 13. Behavior Notebook
- [x] Narrative first → Trace second.
- [x] Behavior / Flow / State / Raw use real PaperTab components.
- [x] Summary/evidence use real StickyNote components.
- [x] Search/filter/status/empty/loading/error use shared UI.
- [x] Technical evidence uses InspectorSection and receipt treatment.

### 14. Provider Calls
- [x] Provider evidence reads as technical receipt material.
- [x] Dense technical view intentionally keeps low scrapbook intensity.
- [x] Shared tokens / status language are inherited from the technical evidence system.

### 15. Runtime Raw
- [x] Remains a developer appendix rather than being over-decorated.
- [x] Typography, paper surface, state color, and monospaced raw data are standardized.

### 16. Tool Calling
- [x] Remains an experiment bench inside Toolbox.
- [x] Functional technical density is preserved.
- [x] Shared/final page tokens keep it visually in the same notebook system.

### 17. Schedules
- [x] Reminder records are real StickyNote components.
- [x] Status/select/refresh/auto-refresh/pagination use shared UI.
- [x] Empty/loading/error states use shared UI.
- [x] Existing adaptive polling and cancel semantics are preserved.

### 18. Settings
- [x] Presented as private back pages / creator pocket.
- [x] AccountPanel remains the authoritative account/security component.
- [x] Admin Runtime is surfaced as a separate explicit action.

### 19. Admin Runtime
- [x] Remains a low-decoration technical configuration sheet.
- [x] Final tokens/styles keep it visually related without making technical settings decorative.

### 20. Echo Masque Lab
- [x] Workspace reads as a separate experiment notebook.
- [x] Tabs and cards use a stronger lab scrapbook treatment.
- [x] Evaluation clarity remains more important than decoration.

### 21. Matrix
- [x] Dense comparison/table semantics are preserved.
- [x] Page/tab/card/paper hierarchy is aligned with the experiment notebook.
- [x] No decorative fragmentation of dense analytics.

### 22. Auth / Login
- [x] Reworked as a Studio Pass surface.
- [x] Shared form controls / tabs / feedback used.
- [x] Right-side scrapbook composition communicates project identity.
- [x] All required/translatable copy remains HTML, not baked into imagery.

## Final non-goals / acceptable grandfathering

- Native HTML controls inside legacy dense technical pages are not a release blocker when they remain accessible and visually inherit the final shared tokens. New feature work should use the shared primitives.
- The migration does not add a hard lint error yet; enforcement should become scoped warning/new-code enforcement before a repository-wide error.
- Generated production illustration is not required to merge this UI migration. The contract explicitly permits it when a later illustration materially improves Dashboard/Auth/empty-state identity.
- No Runtime behavior, Topic decision logic, Smart Participation authority, provider request semantics, or Discord-native rendering behavior is changed by this UI program.
