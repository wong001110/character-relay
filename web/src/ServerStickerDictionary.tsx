import { useEffect, useState, type FormEvent } from "react";
import type { DiscordServerProfile } from "./deploymentApi";
import { expressionCatalogApi, type ExpressionSemantic, type ExpressionSemanticCreate } from "./expressionCatalogApi";
import { Button, FormField, Input, Textarea, Select, PaperCard } from "./components/ui";
interface Props { profile: DiscordServerProfile; demoMode: boolean; zh: boolean; onError: (message: string) => void; }
export function ServerStickerDictionary({ profile, demoMode, zh, onError }: Props) {
  const [items, setItems] = useState<ExpressionSemantic[]>([]);
  const [type, setType] = useState("sticker");
  const [selected, setSelected] = useState<ExpressionSemantic | null>(null);
  const [working, setWorking] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true; setLoading(true); setSelected(null); setItems([]); setError("");
    void expressionCatalogApi.list(profile.connection_id, profile.guild_id).then(value => { if (live) setItems(value); }).catch((e: unknown) => { if (live) setError(String(e)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [profile.connection_id, profile.guild_id, revision]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || working || demoMode) return;
    const data = new FormData(event.currentTarget);
    const { id: _id, resource_key: _key, semantic_source: _source, semantic_confidence: _confidence, last_seen_at: _seen, created_at: _created, updated_at: _updated, ...existing } = selected;
    const payload: ExpressionSemanticCreate = { ...existing, semantic_intent: String(data.get("intent") ?? ""), semantic_emotion: String(data.get("emotion") ?? ""), semantic_description: String(data.get("description") ?? ""), enabled: data.has("enabled") };
    setWorking(true); setError("");
    try { await expressionCatalogApi.save(payload); setRevision(x => x + 1); } catch (e) { setError(String(e)); onError(String(e)); } finally { setWorking(false); }
  }
  return <section className="room-expression-catalog">
    <h3>{zh ? "表情语义目录" : "Expression catalog"}</h3>
    <p>{zh ? "角色先选择表达意图，运行时再按此目录匹配；不运行候选生成工作流。" : "Characters request an intent; the runtime resolves catalog metadata without a candidate-generation workflow."}</p>
    <div className="room-controls"><FormField label={zh ? "资源类型" : "Resource type"}><Select value={type} onChange={e => setType(e.target.value)}><option value="sticker">Sticker</option><option value="emoji">Emoji</option></Select></FormField><Button disabled={working || loading} onClick={() => setRevision(x => x + 1)}>{zh ? "刷新" : "Refresh"}</Button></div>
    {error && <p role="alert" className="error-note">{error}</p>}
    {loading ? <p role="status">{zh ? "读取中…" : "Loading…"}</p> : <div className="room-expression-list">{items.filter(item => item.resource_type === type).map(item => <PaperCard key={item.id}><strong>{item.name || item.resource_id}</strong><p>{item.semantic_description || item.description || "—"}</p><small>{item.semantic_intent || "—"} / {item.semantic_emotion || "—"} · {item.enabled ? "enabled" : "disabled"}</small>{!demoMode && <Button onClick={() => setSelected(item)}>{zh ? "编辑含义" : "Edit meaning"}</Button>}</PaperCard>)}</div>}
    {!loading && !items.some(item => item.resource_type === type) && <p>{zh ? "尚无已同步资源。" : "No synced resources yet."}</p>}
    {selected && !demoMode && <PaperCard><form key={selected.id} onSubmit={e => void save(e)}>
      <h4>{selected.name}</h4>
      <FormField label="Intent"><Input name="intent" defaultValue={selected.semantic_intent} maxLength={120} /></FormField>
      <FormField label="Emotion"><Input name="emotion" defaultValue={selected.semantic_emotion} maxLength={120} /></FormField>
      <FormField label={zh ? "语义描述" : "Semantic description"}><Textarea name="description" defaultValue={selected.semantic_description} maxLength={1200} /></FormField>
      <label><input type="checkbox" name="enabled" defaultChecked={selected.enabled} />{zh ? "可供角色使用" : "Available to characters"}</label>
      <div className="room-controls"><Button type="submit" variant="primary" disabled={working}>{zh ? "保存" : "Save"}</Button><Button onClick={() => setSelected(null)}>{zh ? "取消" : "Cancel"}</Button></div>
    </form></PaperCard>}
  </section>;
}
