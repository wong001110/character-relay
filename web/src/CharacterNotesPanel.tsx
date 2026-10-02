import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { CharacterCard } from "./api";
import type { DiscordServerCatalog, DiscordServerProfile } from "./deploymentApi";
import { characterNotesApi, type CharacterNote, type NoteInput, type NoteLocation } from "./characterNotesApi";
import { Button, FormField, Input, Select, Textarea, PaperCard, StickyNote } from "./components/ui";

interface Props { cards: CharacterCard[]; profile: DiscordServerProfile; catalog?: DiscordServerCatalog | null; demoMode: boolean; zh: boolean; }
export function CharacterNotesPanel({ cards, profile, catalog, demoMode, zh }: Props) {
  const [cardId, setCardId] = useState(cards[0]?.id ?? "");
  const [channel, setChannel] = useState("");
  const [notes, setNotes] = useState<CharacterNote[]>([]);
  const [editing, setEditing] = useState<CharacterNote | null>(null);
  const [subject, setSubject] = useState("self");
  const [kind, setKind] = useState<NoteInput["kind"]>("note");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const location = useMemo<NoteLocation | null>(() => channel ? { connection_id: profile.connection_id, guild_id: profile.guild_id, channel_id: channel, thread_id: "" } : null, [channel, profile.connection_id, profile.guild_id]);
  useEffect(() => { setChannel(""); }, [profile.id]);
  useEffect(() => {
    let live = true;
    setNotes([]); setEditing(null); setText(""); setError("");
    if (!cardId) return;
    setLoading(true);
    void characterNotesApi.list(cardId, location).then(value => { if (live) setNotes(value); }).catch((e: unknown) => { if (live) setError(String(e)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [cardId, location, revision]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (working || demoMode || !cardId) return;
    setWorking(true); setError("");
    try {
      const input: NoteInput = { subject_ref: subject.trim(), kind, text: text.trim() };
      if (editing) await characterNotesApi.update(cardId, editing, input);
      else await characterNotesApi.create(cardId, input, location);
      setEditing(null); setText(""); setRevision(x => x + 1);
    } catch (e) { setError(String(e)); } finally { setWorking(false); }
  }
  async function forget(note: CharacterNote) {
    if (working || demoMode || !window.confirm(zh ? "忘记这条笔记？" : "Forget this note?")) return;
    setWorking(true); setError("");
    try { await characterNotesApi.forget(cardId, note); setRevision(x => x + 1); } catch (e) { setError(String(e)); } finally { setWorking(false); }
  }
  return <section className="room-notes-panel" aria-label={zh ? "明确笔记与关系" : "Explicit notes and relationships"}>
    <PaperCard><h2>{zh ? "明确笔记与关系" : "Explicit notes and relationships"}</h2>
      <p>{zh ? "只保存明确内容，不计算亲密度。背景笔记由作者明确设定；房间笔记只在所选位置可用。" : "Explicit text, not closeness scores. Author-defined background is deliberate; room notes remain scoped to the selected destination."}</p>
      <div className="room-controls">
        <FormField label={zh ? "角色" : "Character"}><Select value={cardId} onChange={e => setCardId(e.target.value)}>{cards.map(card => <option key={card.id} value={card.id}>{card.display_name}</option>)}</Select></FormField>
        <FormField label={zh ? "可见范围" : "Visibility"}><Select value={channel} onChange={e => setChannel(e.target.value)}><option value="">{zh ? "作者背景（跨房间）" : "Authored background (cross-room)"}</option>{catalog?.channels.map(item => <option key={item.id} value={item.id}>#{item.name}</option>)}</Select></FormField>
      </div>
      <Button onClick={() => setRevision(x => x + 1)} disabled={loading || working}>{zh ? "刷新" : "Refresh"}</Button>
    </PaperCard>
    {error && <p role="alert" className="error-note">{error}</p>}
    {loading ? <p role="status">{zh ? "读取中…" : "Loading…"}</p> : <div className="room-note-list">{notes.map(note => <PaperCard key={note.id}>
      <strong>{note.subject_ref} · {note.kind}</strong><p className="room-preserve-text">{note.text}</p>
      <small>{note.authored ? (zh ? "作者设定" : "Authored") : (zh ? "成员明确记录" : "Explicit member note")} · v{note.version} · {new Date(note.updated_at).toLocaleString()}</small>
      {!demoMode && <div className="room-controls"><Button disabled={working} onClick={() => { setEditing(note); setSubject(note.subject_ref); setKind(note.kind); setText(note.text); }}>{zh ? "编辑" : "Edit"}</Button><Button variant="danger" disabled={working} onClick={() => void forget(note)}>{zh ? "忘记" : "Forget"}</Button></div>}
    </PaperCard>)}{!notes.length && <p>{zh ? "此范围没有笔记。" : "No notes in this scope."}</p>}</div>}
    {!demoMode && <PaperCard><form onSubmit={e => void save(e)}>
      <h3>{editing ? (zh ? "修正笔记" : "Correct note") : (zh ? "新增明确笔记" : "Add explicit note")}</h3>
      <FormField label={zh ? "对象 ID" : "Subject ID"} hint="self / user:ID / character:ID"><Input required value={subject} onChange={e => setSubject(e.target.value)} maxLength={200} /></FormField>
      <FormField label={zh ? "类型" : "Kind"}><Select value={kind} onChange={e => setKind(e.target.value as NoteInput["kind"])}><option value="note">{zh ? "笔记" : "Note"}</option><option value="relationship">{zh ? "关系备注明文" : "Relationship note"}</option></Select></FormField>
      <FormField label={zh ? "内容" : "Text"}><Textarea required maxLength={800} value={text} onChange={e => setText(e.target.value)} rows={4} /></FormField>
      <div className="room-controls"><Button type="submit" variant="primary" disabled={working || loading || !cardId || !text.trim()}>{working ? (zh ? "保存中…" : "Saving…") : (zh ? "保存" : "Save")}</Button>{editing && <Button onClick={() => { setEditing(null); setText(""); }}>{zh ? "取消编辑" : "Cancel edit"}</Button>}</div>
    </form></PaperCard>}
    {demoMode && <StickyNote>{zh ? "演示模式只读。" : "Demo is read-only."}</StickyNote>}
  </section>;
}
