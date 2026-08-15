# ruff: noqa
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor: {path}: {old[:80]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"non-unique patch anchor: {path}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/echo_masque/api/routes/__init__.py",
    "from echo_masque.api.routes.comparisons import router as comparisons_router\nfrom echo_masque.api.routes.connectors import router as connectors_router\n",
    "from echo_masque.api.routes.comparisons import router as comparisons_router\nfrom echo_masque.api.routes.connectors import router as connectors_router\nfrom echo_masque.api.routes.conversation_intelligence import (\n    router as conversation_intelligence_router,\n)\n",
)
replace_once(
    "src/echo_masque/api/routes/__init__.py",
    '    "comparisons_router",\n    "connectors_router",\n',
    '    "comparisons_router",\n    "connectors_router",\n    "conversation_intelligence_router",\n',
)

replace_once(
    "src/echo_masque/api/app.py",
    "    comparisons_router,\n    connectors_router,\n",
    "    comparisons_router,\n    connectors_router,\n    conversation_intelligence_router,\n",
)
replace_once(
    "src/echo_masque/api/app.py",
    "    app.include_router(interactions_router)\n    app.include_router(smart_participation_router)\n",
    "    app.include_router(interactions_router)\n    app.include_router(smart_participation_router)\n    app.include_router(conversation_intelligence_router)\n",
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    'import { DiscordEventLogPanel } from "./DiscordEventLogPanel";\n',
    'import { ConversationIntelligenceInspector } from "./ConversationIntelligenceInspector";\nimport { DiscordEventLogPanel } from "./DiscordEventLogPanel";\n',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    'type ServerNotebookTab = "characters" | "knowledge" | "interactions";\n',
    'type ServerNotebookTab = "characters" | "knowledge" | "interactions" | "intelligence";\n',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''          <button
            type="button"
            className={serverNotebookTab === "interactions" ? "is-active" : ""}
            onClick={() => setServerNotebookTab("interactions")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">⌁</span>
            <strong>{zh ? "角色互动" : "Interactions"}</strong>
          </button>
''',
    '''          <button
            type="button"
            className={serverNotebookTab === "interactions" ? "is-active" : ""}
            onClick={() => setServerNotebookTab("interactions")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">⌁</span>
            <strong>{zh ? "角色互动" : "Interactions"}</strong>
          </button>
          <button
            type="button"
            className={serverNotebookTab === "intelligence" ? "is-active" : ""}
            onClick={() => setServerNotebookTab("intelligence")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">◉</span>
            <strong>{zh ? "对话智能" : "Intelligence"}</strong>
          </button>
''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''          {serverNotebookTab === "interactions" && selectedWorkspaceProfile && (
            <InteractionSessionsPanel
              demoMode={demoMode}
              zh={zh}
              serverProfile={selectedWorkspaceProfile}
              serverCatalog={selectedWorkspaceCatalog}
            />
          )}

          {serverNotebookTab !== "characters" && !selectedWorkspaceProfile && (
''',
    '''          {serverNotebookTab === "interactions" && selectedWorkspaceProfile && (
            <InteractionSessionsPanel
              demoMode={demoMode}
              zh={zh}
              serverProfile={selectedWorkspaceProfile}
              serverCatalog={selectedWorkspaceCatalog}
            />
          )}

          {serverNotebookTab === "intelligence" && selectedWorkspaceProfile && (
            <ConversationIntelligenceInspector
              cards={cards}
              profile={selectedWorkspaceProfile}
              catalog={selectedWorkspaceCatalog}
              zh={zh}
            />
          )}

          {serverNotebookTab !== "characters" && !selectedWorkspaceProfile && (
''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '{zh ? "Knowledge 与 Interaction 都属于当前 Server。" : "Knowledge and Interactions are scoped to the selected Server."}',
    '{zh ? "Knowledge、Interaction 与 Intelligence 都属于当前 Server。" : "Knowledge, Interactions, and Intelligence are scoped to the selected Server."}',
)

styles = Path("web/src/styles.css")
css = styles.read_text(encoding="utf-8")
marker = "/* Conversation Intelligence Inspector */"
if marker in css:
    raise SystemExit("Conversation Intelligence Inspector styles already exist")
css += r'''

/* Conversation Intelligence Inspector */
.conversation-intelligence-inspector { display: grid; gap: 18px; }
.conversation-intelligence-head { padding: 22px; }
.conversation-intelligence-head h2 { margin: 6px 0 8px; }
.conversation-intelligence-head p { margin: 0; max-width: 860px; color: var(--muted-text); }
.conversation-intelligence-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr); gap: 18px; align-items: start; }
.intelligence-character-panel, .intelligence-topic-panel { padding: 20px; min-width: 0; }
.intelligence-panel-heading { display: flex; align-items: end; justify-content: space-between; gap: 14px; margin-bottom: 14px; }
.intelligence-panel-heading > div { display: grid; gap: 3px; }
.intelligence-panel-heading span, .intelligence-section-title small { color: var(--muted-text); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
.intelligence-panel-heading select { max-width: 240px; }
.intelligence-authority-note { border: 1px dashed var(--line); border-radius: 14px; padding: 14px; background: color-mix(in srgb, var(--paper) 82%, white 18%); margin-bottom: 16px; }
.intelligence-authority-note p { margin: 7px 0 10px; color: var(--muted-text); }
.intelligence-chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.intelligence-chip-row span { border: 1px solid var(--line); border-radius: 999px; padding: 4px 8px; font-size: .76rem; background: var(--paper); }
.intelligence-section-title { display: flex; align-items: center; justify-content: space-between; margin: 14px 0 10px; }
.intelligence-section-title > div { display: grid; gap: 3px; }
.learned-state-list { display: grid; gap: 9px; }
.learned-state-card { border: 1px solid var(--line); border-radius: 14px; background: var(--paper); overflow: hidden; }
.learned-state-card summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; padding: 12px 14px; list-style: none; }
.learned-state-card summary::-webkit-details-marker { display: none; }
.learned-state-card summary > div:first-child { display: grid; gap: 2px; }
.learned-state-card summary span { color: var(--muted-text); font-size: .76rem; text-transform: uppercase; letter-spacing: .05em; }
.learned-state-value { text-align: right; display: grid; }
.learned-state-value strong { font-size: 1.05rem; }
.learned-state-value small { color: var(--muted-text); }
.learned-state-meter { position: relative; height: 6px; margin: 0 14px 14px; background: linear-gradient(90deg, rgba(177,92,92,.14), rgba(130,130,130,.08) 50%, rgba(78,126,91,.14)); border-radius: 999px; }
.learned-state-meter .learned-state-zero { position: absolute; left: 50%; top: -3px; width: 1px; height: 12px; background: var(--line); }
.learned-state-meter i { position: absolute; top: -3px; width: 8px; height: 12px; border-radius: 999px; background: currentColor; transform: translateX(-50%); }
.learned-state-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 0 14px 12px; }
.learned-state-metrics > div { display: grid; gap: 2px; padding: 8px; border-radius: 10px; background: var(--soft-panel); }
.learned-state-metrics span { color: var(--muted-text); font-size: .72rem; }
.learned-state-last-evidence { padding: 0 14px 10px; margin: 0; color: var(--muted-text); font-size: .78rem; }
.learned-state-provenance { border-top: 1px solid var(--line); padding: 12px 14px 14px; display: grid; gap: 8px; }
.learned-state-provenance article { display: grid; gap: 3px; padding: 9px; background: var(--soft-panel); border-radius: 10px; }
.learned-state-provenance article > div { display: flex; justify-content: space-between; gap: 10px; }
.learned-state-provenance small { color: var(--muted-text); }
.learned-state-provenance code { overflow-wrap: anywhere; font-size: .7rem; }
.learned-state-provenance .is-positive { color: #3f7851; }
.learned-state-provenance .is-negative { color: #9a4d4d; }
.current-topic-card { border: 1px solid var(--line); border-radius: 16px; padding: 16px; background: var(--paper); }
.current-topic-status { display: flex; align-items: center; gap: 7px; color: var(--muted-text); font-size: .76rem; text-transform: uppercase; letter-spacing: .06em; }
.current-topic-status span { width: 8px; height: 8px; border-radius: 50%; background: #4f8a61; box-shadow: 0 0 0 4px rgba(79,138,97,.12); }
.current-topic-card h3 { margin: 8px 0 6px; }
.current-topic-card > p { color: var(--muted-text); }
.topic-meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
.topic-meta-grid > div { display: grid; gap: 3px; padding: 9px; border-radius: 10px; background: var(--soft-panel); }
.topic-meta-grid span { color: var(--muted-text); font-size: .72rem; }
.topic-meta-grid strong { font-size: .82rem; overflow-wrap: anywhere; }
.topic-open-loops { margin-top: 12px; }
.topic-open-loops ul { margin: 6px 0 0; padding-left: 20px; }
.topic-timeline { margin-top: 16px; display: grid; gap: 0; }
.topic-timeline-item { position: relative; display: grid; grid-template-columns: 18px 1fr; gap: 10px; padding: 5px 0 15px; }
.topic-timeline-item::before { content: ""; position: absolute; left: 5px; top: 15px; bottom: -5px; width: 1px; background: var(--line); }
.topic-timeline-item:last-of-type::before { display: none; }
.topic-timeline-dot { width: 11px; height: 11px; margin-top: 3px; border-radius: 50%; border: 2px solid var(--paper); background: #aaa; box-shadow: 0 0 0 1px var(--line); z-index: 1; }
.topic-timeline-item.is-active .topic-timeline-dot { background: #4f8a61; }
.topic-timeline-item.is-cooling .topic-timeline-dot { background: #c39a52; }
.topic-timeline-heading { display: flex; justify-content: space-between; gap: 10px; }
.topic-timeline-heading span { color: var(--muted-text); font-size: .72rem; text-transform: uppercase; }
.topic-timeline-item p { margin: 4px 0; color: var(--muted-text); font-size: .82rem; }
.topic-timeline-item small { color: var(--muted-text); }
@media (max-width: 980px) { .conversation-intelligence-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .intelligence-panel-heading { align-items: stretch; flex-direction: column; } .intelligence-panel-heading select { max-width: none; } .learned-state-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
'''
styles.write_text(css, encoding="utf-8")
