import { useEffect, useState, type FormEvent } from "react";

import type { DiscordServerProfile } from "./deploymentApi";
import { interactionApi, type StickerSemantic } from "./interactionApi";

interface Props {
  profile: DiscordServerProfile;
  demoMode: boolean;
  zh: boolean;
  onError: (message: string) => void;
}

export function ServerStickerDictionary({ profile, demoMode, zh, onError }: Props) {
  const [stickers, setStickers] = useState<StickerSemantic[]>([]);
  const [editing, setEditing] = useState<StickerSemantic | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setStickers(await interactionApi.listStickers(profile.connection_id, profile.guild_id));
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setEditing(null);
    void load();
  }, [profile.connection_id, profile.guild_id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    try {
      setWorking(true);
      await interactionApi.saveSticker({
        connection_id: editing.connection_id,
        guild_id: editing.guild_id,
        sticker_id: editing.sticker_id,
        name: editing.name,
        description: editing.description,
        tags: editing.tags,
        format_type: editing.format_type,
        asset_url: editing.asset_url,
        semantic_intent:
          String(data.get("semantic_intent") ?? "sticker_reaction").trim() ||
          "sticker_reaction",
        semantic_emotion: String(data.get("semantic_emotion") ?? "").trim(),
        semantic_description: String(data.get("semantic_description") ?? "").trim()
      });
      setEditing(null);
      await load();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="server-sticker-section">
      <div className="server-drawer-section-heading">
        <div>
          <p className="tape-label">SERVER STICKERS</p>
          <h3>{zh ? "Sticker Dictionary" : "Sticker dictionary"}</h3>
          <p>
            {zh
              ? "Connector 会自动同步当前 Server 的自定义 Sticker。这里只编辑角色应理解的含义，不需要填写 Server ID 或 Sticker ID。"
              : "The connector synchronizes this Server's custom Stickers. Edit only the meaning supplied to characters; Server and Sticker IDs are automatic."}
          </p>
        </div>
        <span className="server-sticker-count">{stickers.length}</span>
      </div>

      {loading ? (
        <div className="server-sticker-empty">{zh ? "正在同步 Sticker…" : "Loading Stickers…"}</div>
      ) : stickers.length ? (
        <div className="server-sticker-grid">
          {stickers.map((item) => (
            <article className="server-sticker-card" key={item.id}>
              <div className="server-sticker-preview">
                {item.asset_url ? (
                  <img src={item.asset_url} alt="" loading="lazy" />
                ) : (
                  <span aria-hidden="true">✦</span>
                )}
              </div>
              <div className="server-sticker-copy">
                <div className="server-sticker-title-row">
                  <strong>{item.name}</strong>
                  <span className={`sticker-source source-${item.semantic_source}`}>
                    {item.semantic_source}
                  </span>
                </div>
                <small>{item.description || item.tags.join(", ") || `ID ${item.sticker_id}`}</small>
                <p>
                  {item.semantic_description ||
                    (zh ? "尚未配置角色语义。" : "No character meaning configured yet.")}
                </p>
                <div className="server-sticker-meta">
                  <span>{item.semantic_intent || "sticker_reaction"}</span>
                  <span>{item.semantic_emotion || "—"}</span>
                  <span>{Math.round(item.semantic_confidence * 100)}%</span>
                </div>
              </div>
              {!demoMode && (
                <button className="paper-button" type="button" onClick={() => setEditing(item)}>
                  {zh ? "编辑含义" : "Edit meaning"}
                </button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="server-sticker-empty">
          <strong>{zh ? "这个 Server 暂时没有可用 Sticker" : "No available Stickers in this Server"}</strong>
          <p>
            {zh
              ? "Connector 下次同步 Server 时会自动获取，不需要先在聊天中发送。"
              : "The connector will fetch them during the next Server sync; they do not need to be sent first."}
          </p>
        </div>
      )}

      {editing && !demoMode && (
        <form className="sticker-meaning-editor" onSubmit={save} key={editing.id}>
          <div className="sticker-editor-identity">
            <div className="server-sticker-preview compact">
              {editing.asset_url ? <img src={editing.asset_url} alt="" /> : <span>✦</span>}
            </div>
            <div>
              <strong>{editing.name}</strong>
              <small>{profile.guild_name} · {editing.sticker_id}</small>
            </div>
            <button className="text-button" type="button" onClick={() => setEditing(null)}>
              {zh ? "取消" : "Cancel"}
            </button>
          </div>
          <div className="sticker-editor-fields">
            <label>
              Intent
              <input
                name="semantic_intent"
                defaultValue={editing.semantic_intent || "sticker_reaction"}
              />
            </label>
            <label>
              Emotion
              <input
                name="semantic_emotion"
                defaultValue={editing.semantic_emotion}
                placeholder="amused / shy / annoyed"
              />
            </label>
            <label className="drawer-form-wide">
              {zh ? "角色应理解的含义" : "Meaning supplied to characters"}
              <textarea
                name="semantic_description"
                rows={4}
                required
                defaultValue={editing.semantic_description}
              />
            </label>
          </div>
          <button className="ink-button" disabled={working}>
            {working ? (zh ? "保存中…" : "Saving…") : zh ? "保存角色语义" : "Save character meaning"}
          </button>
        </form>
      )}
    </section>
  );
}
