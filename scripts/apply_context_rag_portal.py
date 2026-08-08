from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/DeploymentCenter.tsx",
    'import { InteractionSessionsPanel } from "./InteractionSessionsPanel";\n'
    'import { SmartParticipationStudio } from "./SmartParticipationStudio";\n',
    'import { InteractionSessionsPanel } from "./InteractionSessionsPanel";\n'
    'import { KnowledgeBasePanel } from "./KnowledgeBasePanel";\n'
    'import { SmartParticipationStudio } from "./SmartParticipationStudio";\n',
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    '''      <DiscordServerProfilesPanel\n        connections={connections}\n        profiles={serverProfiles}\n        catalog={serverCatalog}\n        selectedProfileId={selectedServerProfileId}\n        demoMode={demoMode}\n        zh={zh}\n        onSelectProfile={setSelectedServerProfileId}\n        onChanged={load}\n        onError={(message) => setError(message || null)}\n        onOpenLogs={() => setEventLogOpen(true)}\n      />\n\n      <section className="deployment-summary-grid">''',
    '''      <DiscordServerProfilesPanel\n        connections={connections}\n        profiles={serverProfiles}\n        catalog={serverCatalog}\n        selectedProfileId={selectedServerProfileId}\n        demoMode={demoMode}\n        zh={zh}\n        onSelectProfile={setSelectedServerProfileId}\n        onChanged={load}\n        onError={(message) => setError(message || null)}\n        onOpenLogs={() => setEventLogOpen(true)}\n      />\n\n      <KnowledgeBasePanel\n        profile={selectedWorkspaceProfile}\n        catalog={selectedWorkspaceCatalog}\n        cards={cards}\n        demoMode={demoMode}\n        zh={zh}\n      />\n\n      <section className="deployment-summary-grid">''',
)

css_path = Path("web/src/deployments.css")
css = css_path.read_text(encoding="utf-8")
marker = "/* Context Layer / RAG V1 */"
if marker not in css:
    css += r'''

/* Context Layer / RAG V1 */
.knowledge-panel {
  max-width: 1440px;
  margin: 0 auto 24px;
  padding: 24px;
}

.knowledge-panel-heading {
  align-items: flex-start;
  gap: 24px;
}

.knowledge-panel-heading p:last-child {
  max-width: 760px;
  margin-bottom: 0;
}

.knowledge-create-form {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(180px, 0.7fr) minmax(220px, 1fr);
  gap: 14px;
  margin: 18px 0;
  padding: 18px;
  border: 1px dashed rgba(73, 61, 87, 0.24);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.34);
}

.knowledge-create-form label,
.knowledge-document-form label {
  display: grid;
  gap: 7px;
  font-size: 0.86rem;
  font-weight: 700;
}

.knowledge-description-field,
.knowledge-create-form .ink-button {
  align-self: end;
}

.knowledge-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(340px, 1.2fr);
  gap: 18px;
  margin-top: 18px;
}

.knowledge-base-list,
.knowledge-document-panel,
.knowledge-playground {
  border: 1px solid rgba(73, 61, 87, 0.16);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.3);
}

.knowledge-base-list {
  display: grid;
  gap: 10px;
  align-content: start;
  padding: 12px;
}

.knowledge-base-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 13px;
  border: 1px solid transparent;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
}

.knowledge-base-card.is-selected {
  border-color: rgba(95, 77, 127, 0.42);
  box-shadow: 0 8px 20px rgba(54, 42, 72, 0.08);
}

.knowledge-base-card > div:first-child {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.knowledge-base-card span,
.knowledge-base-card small,
.knowledge-document-list span,
.knowledge-document-list small,
.knowledge-playground small {
  color: var(--muted-ink, #716977);
}

.knowledge-card-actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.knowledge-document-panel {
  padding: 16px;
}

.knowledge-document-form {
  display: grid;
  gap: 12px;
  margin: 14px 0;
  padding: 14px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.48);
}

.knowledge-document-form textarea {
  resize: vertical;
  min-height: 150px;
}

.knowledge-document-list {
  display: grid;
  gap: 9px;
  margin-top: 12px;
}

.knowledge-document-list article {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 4px;
  border-bottom: 1px dashed rgba(73, 61, 87, 0.18);
}

.knowledge-document-list article > div {
  display: grid;
  gap: 3px;
}

.knowledge-playground {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  padding: 16px;
}

.knowledge-playground-heading {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.knowledge-playground-heading > div {
  display: grid;
  gap: 4px;
}

.knowledge-playground-controls {
  display: grid;
  grid-template-columns: minmax(220px, 1.6fr) minmax(180px, 1fr) minmax(160px, 0.8fr) auto;
  gap: 10px;
}

.knowledge-hit-list {
  display: grid;
  gap: 10px;
}

.knowledge-hit-list article {
  padding: 13px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.54);
}

.knowledge-hit-list article p {
  margin-bottom: 0;
  white-space: pre-wrap;
}

.knowledge-hit-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
  font-size: 0.84rem;
}

@media (max-width: 900px) {
  .knowledge-layout,
  .knowledge-create-form,
  .knowledge-playground-controls {
    grid-template-columns: 1fr;
  }
}
'''
    css_path.write_text(css, encoding="utf-8")

print("Knowledge Base Portal integration applied.")
