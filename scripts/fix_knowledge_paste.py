from pathlib import Path

panel_path = Path("web/src/KnowledgeBasePanel.tsx")
css_path = Path("web/src/deployments.css")

panel = panel_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

old = '''  function setScope(scope: KnowledgeScopeType) {
    setBaseDraft((current) => ({
      ...current,
      scope_type: scope,
      connection_id: scope === "global" ? "" : profile?.connection_id ?? "",
      guild_id: scope === "global" ? "" : profile?.guild_id ?? "",
      channel_id: scope === "channel" ? current.channel_id : "",
      thread_id: scope === "channel" ? current.thread_id : ""
    }));
  }
'''
new = old + '''\n  function updateBaseDraft(patch: Partial<KnowledgeBaseWrite>) {
    setBaseDraft((current) => ({ ...current, ...patch }));
  }
'''
assert panel.count(old) == 1
panel = panel.replace(old, new, 1)

old = '''  async function addDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBase) return;
    const data = new FormData(event.currentTarget);
'''
new = '''  async function addDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBase) return;
    const form = event.currentTarget;
    const data = new FormData(form);
'''
assert panel.count(old) == 1
panel = panel.replace(old, new, 1)

old = '''      setDocumentOpen(false);
      event.currentTarget.reset();
      await loadDocuments(selectedBase.id);
'''
new = '''      setDocumentOpen(false);
      form.reset();
      await loadDocuments(selectedBase.id);
'''
assert panel.count(old) == 1
panel = panel.replace(old, new, 1)

replacements = {
'''              onChange={(event) =>
                setBaseDraft((current) => ({ ...current, name: event.currentTarget.value }))
              }
''': '''              onChange={(event) => updateBaseDraft({ name: event.currentTarget.value })}
''',
'''                onChange={(event) =>
                  setBaseDraft((current) => ({
                    ...current,
                    channel_id: event.currentTarget.value
                  }))
                }
''': '''                onChange={(event) => updateBaseDraft({ channel_id: event.currentTarget.value })}
''',
'''              onChange={(event) =>
                setBaseDraft((current) => ({
                  ...current,
                  character_card_id: event.currentTarget.value
                }))
              }
''': '''              onChange={(event) =>
                updateBaseDraft({ character_card_id: event.currentTarget.value })
              }
''',
}
for source, target in replacements.items():
    assert panel.count(source) == 1, source
    panel = panel.replace(source, target, 1)

old = '''          <label className="knowledge-description-field">
            {zh ? "说明（可选）" : "Description (optional)"}
            <input
              maxLength={4000}
              value={baseDraft.description}
              onChange={(event) =>
                setBaseDraft((current) => ({
                  ...current,
                  description: event.currentTarget.value
                }))
              }
            />
          </label>
'''
new = '''          <label className="knowledge-description-field">
            {zh ? "说明（可选）" : "Description (optional)"}
            <textarea
              rows={5}
              maxLength={4000}
              value={baseDraft.description}
              onChange={(event) => updateBaseDraft({ description: event.currentTarget.value })}
              placeholder={
                zh
                  ? "简要说明这个 Knowledge Base 的用途。实际知识内容请在建立后用“+ 文档”加入。"
                  : "Briefly describe this knowledge base. Add the actual knowledge with + Document after creation."
              }
            />
            <small>
              {zh
                ? "这里是知识库说明，不是 RAG 正文；FAQ、角色背景、Lore 等请放进文档。"
                : "This describes the knowledge base; put FAQ, character background, lore, and other RAG content in documents."}
            </small>
          </label>
'''
assert panel.count(old) == 1
panel = panel.replace(old, new, 1)

old = '''              </div>

              {documentOpen && !demoMode && (
'''
new = '''              </div>

              {selectedBase.description && (
                <p className="knowledge-base-description">{selectedBase.description}</p>
              )}

              {documentOpen && !demoMode && (
'''
assert panel.count(old) == 1
panel = panel.replace(old, new, 1)

css_anchor = '''.knowledge-description-field,
.knowledge-create-form .ink-button {
  align-self: end;
}
'''
css_new = '''.knowledge-description-field,
.knowledge-create-form .ink-button {
  align-self: end;
}

.knowledge-description-field {
  grid-column: 1 / -1;
}

.knowledge-description-field textarea {
  width: 100%;
  min-height: 120px;
  padding: 10px 12px;
  resize: vertical;
  border: 1px solid rgba(41, 35, 48, 0.2);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  color: inherit;
  font: inherit;
  line-height: 1.5;
}

.knowledge-description-field small {
  color: var(--muted-ink, #716977);
  font-weight: 400;
  line-height: 1.45;
}

.knowledge-base-description {
  margin: -4px 0 14px;
  padding: 10px 12px;
  border-left: 3px solid rgba(95, 77, 127, 0.38);
  border-radius: 0 8px 8px 0;
  background: rgba(95, 77, 127, 0.06);
  color: var(--muted-ink, #716977);
  line-height: 1.55;
  white-space: pre-wrap;
}
'''
assert css.count(css_anchor) == 1
css = css.replace(css_anchor, css_new, 1)

panel_path.write_text(panel, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
print("Knowledge Base paste and textarea fixes applied.")
