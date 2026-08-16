import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard } from "./api";
import {
  Button,
  EmptyState,
  FormField,
  Input,
  SearchField,
  Select,
  Spinner,
  StatusIndicator,
  StickyLabel,
  Textarea,
  Toast
} from "./components/ui";
import type { DiscordServerCatalog, DiscordServerProfile } from "./deploymentApi";
import {
  knowledgeApi,
  type KnowledgeBase,
  type KnowledgeBaseWrite,
  type KnowledgeDocument,
  type KnowledgeRetrieveResult,
  type KnowledgeScopeType
} from "./knowledgeApi";

interface Props {
  profile: DiscordServerProfile | undefined;
  catalog: DiscordServerCatalog | undefined;
  cards: CharacterCard[];
  demoMode: boolean;
  zh: boolean;
}

function formatTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function belongsToProfile(base: KnowledgeBase, profile: DiscordServerProfile): boolean {
  return base.scope_type === "global" || (base.connection_id === profile.connection_id && base.guild_id === profile.guild_id);
}

function scopeLabel(base: KnowledgeBase, catalog: DiscordServerCatalog | undefined, zh: boolean) {
  if (base.scope_type === "global") return zh ? "账号全局" : "Account global";
  if (base.scope_type === "server") return zh ? "当前 Server" : "Current server";
  const channel = catalog?.channels.find((item) => item.id === base.channel_id);
  const label = channel ? `#${channel.name}` : base.channel_id;
  return base.thread_id ? `${label} / ${base.thread_id}` : label;
}

function emptyBase(profile: DiscordServerProfile | undefined): KnowledgeBaseWrite {
  return { name: "", description: "", scope_type: "server", connection_id: profile?.connection_id ?? "", guild_id: profile?.guild_id ?? "", channel_id: "", thread_id: "", character_card_id: "", enabled: true };
}

export function KnowledgeBasePanel({ profile, catalog, cards, demoMode, zh }: Props) {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selectedBaseId, setSelectedBaseId] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [baseDraft, setBaseDraft] = useState<KnowledgeBaseWrite>(() => emptyBase(profile));
  const [createOpen, setCreateOpen] = useState(false);
  const [documentOpen, setDocumentOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [queryChannelId, setQueryChannelId] = useState("");
  const [queryCharacterId, setQueryCharacterId] = useState("");
  const [retrieval, setRetrieval] = useState<KnowledgeRetrieveResult | null>(null);

  const visibleBases = useMemo(() => (profile ? bases.filter((item) => belongsToProfile(item, profile)) : []), [bases, profile]);
  const selectedBase = visibleBases.find((item) => item.id === selectedBaseId) ?? null;

  async function loadBases() {
    if (!profile) { setBases([]); setSelectedBaseId(""); setLoading(false); return; }
    try {
      setLoading(true);
      const next = await knowledgeApi.listBases();
      setBases(next);
      const visible = next.filter((item) => belongsToProfile(item, profile));
      setSelectedBaseId((current) => visible.some((item) => item.id === current) ? current : visible[0]?.id ?? "");
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  }

  async function loadDocuments(baseId: string) {
    if (!baseId) { setDocuments([]); return; }
    try { setDocuments(await knowledgeApi.listDocuments(baseId)); }
    catch (reason) { setDocuments([]); setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  useEffect(() => { setBaseDraft(emptyBase(profile)); setRetrieval(null); setQueryChannelId(""); void loadBases(); }, [profile?.id]);
  useEffect(() => { void loadDocuments(selectedBaseId); }, [selectedBaseId]);

  function setScope(scope: KnowledgeScopeType) {
    setBaseDraft((current) => ({ ...current, scope_type: scope, connection_id: scope === "global" ? "" : profile?.connection_id ?? "", guild_id: scope === "global" ? "" : profile?.guild_id ?? "", channel_id: scope === "channel" ? current.channel_id : "", thread_id: scope === "channel" ? current.thread_id : "" }));
  }
  function updateBaseDraft(patch: Partial<KnowledgeBaseWrite>) { setBaseDraft((current) => ({ ...current, ...patch })); }

  async function createBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!profile) return;
    try { setWorking(true); setError(null); const created = await knowledgeApi.createBase(baseDraft); setCreateOpen(false); setBaseDraft(emptyBase(profile)); await loadBases(); setSelectedBaseId(created.id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function toggleBase(base: KnowledgeBase) {
    try {
      setWorking(true);
      const payload: KnowledgeBaseWrite = { name: base.name, description: base.description, scope_type: base.scope_type, connection_id: base.connection_id, guild_id: base.guild_id, channel_id: base.channel_id, thread_id: base.thread_id, character_card_id: base.character_card_id, enabled: !base.enabled };
      await knowledgeApi.updateBase(base.id, payload); await loadBases();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function removeBase(base: KnowledgeBase) {
    if (!window.confirm(zh ? `删除 Knowledge Base「${base.name}」以及其中所有文档？` : `Delete “${base.name}” and every document inside it?`)) return;
    try { setWorking(true); await knowledgeApi.deleteBase(base.id); await loadBases(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function addDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedBase) return;
    const form = event.currentTarget; const data = new FormData(form);
    try { setWorking(true); await knowledgeApi.createDocument(selectedBase.id, { title: String(data.get("title") ?? "").trim(), content: String(data.get("content") ?? "").trim() }); setDocumentOpen(false); form.reset(); await loadDocuments(selectedBase.id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function removeDocument(document: KnowledgeDocument) {
    if (!window.confirm(zh ? `删除文档「${document.title}」？` : `Delete document “${document.title}”?`)) return;
    try { setWorking(true); await knowledgeApi.deleteDocument(document.id); if (selectedBase) await loadDocuments(selectedBase.id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  async function runRetrieval(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!profile || !query.trim()) return;
    try {
      setWorking(true); setError(null);
      setRetrieval(await knowledgeApi.retrieve({ query: query.trim(), connection_id: profile.connection_id, guild_id: profile.guild_id, channel_id: queryChannelId, thread_id: "", character_card_id: queryCharacterId }));
    } catch (reason) { setRetrieval(null); setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setWorking(false); }
  }

  if (!profile) return <section className="paper-sheet knowledge-panel"><EmptyState title={zh ? "先选择一个 Discord Server" : "Select a Discord server first"} description={zh ? "Knowledge Base 会跟随当前 Server workspace。" : "Knowledge bases follow the current Server workspace."} /></section>;

  return (
    <section className="paper-sheet knowledge-panel knowledge-v3-panel">
      <div className="panel-heading-row knowledge-panel-heading">
        <div><StickyLabel variant="memory">CONTEXT LAYER / RAG V1</StickyLabel><h2>{zh ? "Server 资料夹" : "Server knowledge folder"}</h2><p>{zh ? `为 ${profile.guild_name} 整理可检索资料。Knowledge Base 是文件夹，Document 才是真正进入 RAG 的正文。` : `Organize retrievable material for ${profile.guild_name}. A Knowledge Base is a folder; documents contain the actual RAG content.`}</p></div>
        {!demoMode && <Button variant="secondary" onClick={() => { setBaseDraft(emptyBase(profile)); setCreateOpen((current) => !current); }}>{createOpen ? (zh ? "取消" : "Cancel") : zh ? "+ Knowledge Base" : "+ Knowledge base"}</Button>}
      </div>

      {error && <Toast tone="danger" title={zh ? "Knowledge 操作失败" : "Knowledge operation failed"}>{error}</Toast>}

      {createOpen && !demoMode && (
        <form className="knowledge-create-form" onSubmit={createBase}>
          <FormField label={zh ? "名称" : "Name"} required><Input required maxLength={160} value={baseDraft.name} onChange={(event) => updateBaseDraft({ name: event.currentTarget.value })} placeholder={zh ? "例如：Server FAQ" : "e.g. Server FAQ"} /></FormField>
          <FormField label="Scope"><Select value={baseDraft.scope_type} onChange={(event) => setScope(event.currentTarget.value as KnowledgeScopeType)}><option value="server">{zh ? "当前 Server" : "Current server"}</option><option value="channel">{zh ? "指定 Channel" : "Specific channel"}</option><option value="global">{zh ? "账号全局" : "Account global"}</option></Select></FormField>
          {baseDraft.scope_type === "channel" && <FormField label="Channel" required><Select required value={baseDraft.channel_id} onChange={(event) => updateBaseDraft({ channel_id: event.currentTarget.value })}><option value="">{zh ? "选择 Channel" : "Select channel"}</option>{catalog?.channels.map((channel) => <option value={channel.id} key={channel.id}>#{channel.name}{channel.category_name ? ` · ${channel.category_name}` : ""}</option>)}</Select></FormField>}
          <FormField label={zh ? "角色限制（可选）" : "Character filter (optional)"}><Select value={baseDraft.character_card_id} onChange={(event) => updateBaseDraft({ character_card_id: event.currentTarget.value })}><option value="">{zh ? "所有角色" : "All characters"}</option>{cards.map((card) => <option value={card.id} key={card.id}>{card.display_name}</option>)}</Select></FormField>
          <FormField className="knowledge-description-field" label={zh ? "说明（可选）" : "Description (optional)"} hint={zh ? "这里只说明资料夹用途；FAQ、Lore 与规则请放进 Document。" : "Describe the folder here; put FAQ, lore, and rules in documents."}><Textarea rows={5} maxLength={4000} value={baseDraft.description} onChange={(event) => updateBaseDraft({ description: event.currentTarget.value })} /></FormField>
          <Button variant="primary" disabled={working}>{working ? <><Spinner size="sm" label={zh ? "建立中" : "Creating"} /> {zh ? "建立中…" : "Creating…"}</> : zh ? "建立资料夹" : "Create folder"}</Button>
        </form>
      )}

      <div className="knowledge-layout">
        <div className="knowledge-base-list">
          {loading ? <EmptyState title={zh ? "正在翻资料夹…" : "Opening knowledge folders…"} illustration={<Spinner label={zh ? "读取 Knowledge Base" : "Loading knowledge bases"} />} /> : visibleBases.length === 0 ? <EmptyState title={zh ? "这个 Server 还没有 Knowledge Base" : "No knowledge bases yet"} description={zh ? "建立一个 Server 或 Channel scope 的资料夹，再加入纯文本文档。" : "Create a server- or channel-scoped folder, then add plain-text documents."} /> : visibleBases.map((base) => {
            const character = cards.find((card) => card.id === base.character_card_id);
            return <article key={base.id} className={`knowledge-base-card${selectedBaseId === base.id ? " is-selected" : ""}`} onClick={() => setSelectedBaseId(base.id)}>
              <div><StickyLabel variant="memory">{base.scope_type.toUpperCase()}</StickyLabel><strong>{base.name}</strong><span>{scopeLabel(base, catalog, zh)}</span>{character && <small>{zh ? "角色" : "Character"}: {character.display_name}</small>}</div>
              <StatusIndicator tone={base.enabled ? "success" : "neutral"}>{base.enabled ? (zh ? "启用" : "Enabled") : zh ? "暂停" : "Disabled"}</StatusIndicator>
              {!demoMode && <div className="knowledge-card-actions" onClick={(event) => event.stopPropagation()}><Button variant="ghost" size="sm" disabled={working} onClick={() => void toggleBase(base)}>{base.enabled ? (zh ? "暂停" : "Disable") : zh ? "启用" : "Enable"}</Button><Button variant="ghost" size="sm" disabled={working} onClick={() => void removeBase(base)}>{zh ? "删除" : "Delete"}</Button></div>}
            </article>;
          })}
        </div>

        <div className="knowledge-document-panel">
          {selectedBase ? <>
            <div className="panel-heading-row"><div><strong>{selectedBase.name}</strong><small>{documents.length} {zh ? "份文档" : "documents"}</small></div>{!demoMode && <Button variant="secondary" size="sm" onClick={() => setDocumentOpen((current) => !current)}>{documentOpen ? (zh ? "取消" : "Cancel") : zh ? "+ 文档" : "+ Document"}</Button>}</div>
            {selectedBase.description && <p className="knowledge-base-description">{selectedBase.description}</p>}
            {documentOpen && !demoMode && <form className="knowledge-document-form" onSubmit={addDocument}><FormField label={zh ? "标题" : "Title"} required><Input name="title" required maxLength={240} /></FormField><FormField label={zh ? "纯文本内容" : "Plain-text content"} hint={zh ? "FAQ、角色 Lore、Server 规则或项目知识；RAG V1 会自动分块。" : "FAQ, character lore, server rules, or project knowledge; RAG V1 chunks it automatically."} required><Textarea name="content" required rows={8} maxLength={200000} /></FormField><Button variant="primary" disabled={working}>{working ? (zh ? "处理中…" : "Processing…") : zh ? "加入并分块" : "Add and chunk"}</Button></form>}
            <div className="knowledge-document-list">{documents.map((document) => <article className="knowledge-document-card" key={document.id}><div><StickyLabel variant="neutral">DOCUMENT</StickyLabel><strong>{document.title}</strong><span>{document.chunk_count} chunks · {document.content_chars.toLocaleString()} chars</span><small>{formatTime(document.updated_at)}</small></div>{!demoMode && <Button variant="ghost" size="sm" disabled={working} onClick={() => void removeDocument(document)}>{zh ? "删除" : "Delete"}</Button>}</article>)}{documents.length === 0 && <EmptyState title={zh ? "还没有文档" : "No documents yet"} description={zh ? "知识正文从 Document 开始。" : "Retrievable knowledge begins with a document."} />}</div>
          </> : <EmptyState title={zh ? "选择一个 Knowledge Base" : "Select a knowledge base"} />}
        </div>
      </div>

      <form className="knowledge-playground" onSubmit={runRetrieval}>
        <div className="knowledge-playground-heading"><div><strong>{zh ? "RAG Retrieval Playground" : "RAG retrieval playground"}</strong><small>{zh ? "只测试 scoped retrieval，不调用角色 LLM。" : "Tests scoped retrieval only; no character LLM call is made."}</small></div>{retrieval && <StickyLabel variant="link">{retrieval.hits.length} hits / {retrieval.candidate_chunk_count} candidates</StickyLabel>}</div>
        <div className="knowledge-playground-controls"><SearchField value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder={zh ? "输入检索问题…" : "Enter a retrieval query…"} required /><Select value={queryChannelId} onChange={(event) => setQueryChannelId(event.currentTarget.value)}><option value="">{zh ? "Server scope / 不指定 Channel" : "Server scope / no channel"}</option>{catalog?.channels.map((channel) => <option value={channel.id} key={channel.id}>#{channel.name}</option>)}</Select><Select value={queryCharacterId} onChange={(event) => setQueryCharacterId(event.currentTarget.value)}><option value="">{zh ? "不限角色" : "Any character"}</option>{cards.map((card) => <option value={card.id} key={card.id}>{card.display_name}</option>)}</Select><Button variant="secondary" disabled={working || !query.trim()}>{zh ? "检索" : "Retrieve"}</Button></div>
        {retrieval && <div className="knowledge-hit-list">{retrieval.hits.length === 0 ? <EmptyState title={zh ? "没有达到相关性阈值的 chunk" : "No chunks passed the relevance threshold"} /> : retrieval.hits.map((hit, index) => <article className="knowledge-retrieval-card" key={`${hit.document_id}:${hit.chunk_index}`}><div className="knowledge-hit-meta"><strong>k{index + 1} · {hit.document_title}</strong><StickyLabel variant="link">score {hit.score.toFixed(3)} · chunk {hit.chunk_index}</StickyLabel></div><p>{hit.content}</p></article>)}</div>}
      </form>
    </section>
  );
}