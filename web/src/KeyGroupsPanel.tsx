import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, type CharacterCard } from "./api";
import { useI18n } from "./i18n";
import {
  AUTO_FREE_ANIME_MODEL,
  keyGroupApi,
  type ImageModelScoutResult,
  type KeyGroupCapability,
  type ProviderKeyGroup,
  type ProviderKeyGroupCreate,
  type ProviderKeyGroupUpdate
} from "./keyGroupApi";

const capabilityLabels: Record<KeyGroupCapability, string> = {
  character: "Character / Text",
  media: "Media Understanding",
  image_generation: "Image Generation"
};

const capabilityMarks: Record<KeyGroupCapability, string> = {
  character: "TXT",
  media: "EYE",
  image_generation: "IMG"
};

const providerOptions = [
  ["openrouter", "OpenRouter"],
  ["openai", "OpenAI-compatible"],
  ["deepseek", "DeepSeek"],
  ["custom", "Custom"]
] as const;

interface EditorProps {
  group: ProviderKeyGroup | null;
  creating: boolean;
  working: boolean;
  zh: boolean;
  onSave: (payload: ProviderKeyGroupCreate | ProviderKeyGroupUpdate) => Promise<void>;
  onCancelCreate: () => void;
}

function KeyGroupEditor({
  group,
  creating,
  working,
  zh,
  onSave,
  onCancelCreate
}: EditorProps) {
  const savedImageModel = group?.default_models.image_generation ?? "";
  const [imageMode, setImageMode] = useState<"manual" | "auto">(
    savedImageModel === AUTO_FREE_ANIME_MODEL ? "auto" : "manual"
  );
  const [scout, setScout] = useState<ImageModelScoutResult | null>(null);
  const [scoutMessage, setScoutMessage] = useState<string | null>(null);
  const [scouting, setScouting] = useState(false);

  useEffect(() => {
    setImageMode(savedImageModel === AUTO_FREE_ANIME_MODEL ? "auto" : "manual");
    setScout(null);
    setScoutMessage(null);
  }, [group?.id, savedImageModel]);

  useEffect(() => {
    if (!group || imageMode !== "auto" || group.provider !== "openrouter") return;
    void inspectFreeModels(false);
    // The backend keeps a six-hour cache, so opening this note does not repeatedly hit OpenRouter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group?.id, imageMode]);

  async function inspectFreeModels(refresh: boolean) {
    if (!group) return;
    try {
      setScouting(true);
      setScoutMessage(null);
      const result = await keyGroupApi.scoutImageModels(group.id, refresh);
      setScout(result);
      if (!result.selected_model) {
        setScoutMessage(
          zh
            ? "目前没有找到真正 $0 的 OpenRouter 图片生成 endpoint；自动模式会停止，不会偷切到付费模型。"
            : "No truly $0 OpenRouter image endpoint is available right now. Auto mode stops instead of silently using a paid model."
        );
      }
    } catch (reason) {
      setScoutMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setScouting(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const provider = String(values.get("provider") ?? "").trim();
    if (imageMode === "auto" && provider !== "openrouter") {
      setScoutMessage(
        zh
          ? "自动免费图片模型目前只支持 OpenRouter Key Group。"
          : "Automatic free image discovery currently requires an OpenRouter Key Group."
      );
      return;
    }

    const defaults: Partial<Record<KeyGroupCapability, string>> = {};
    const characterModel = String(values.get("character_model") ?? "").trim();
    const mediaModel = String(values.get("media_model") ?? "").trim();
    const manualImageModel = String(values.get("image_generation_model") ?? "").trim();
    if (characterModel) defaults.character = characterModel;
    if (mediaModel) defaults.media = mediaModel;
    if (imageMode === "auto") {
      defaults.image_generation = AUTO_FREE_ANIME_MODEL;
    } else if (manualImageModel) {
      defaults.image_generation = manualImageModel;
    }

    const apiKey = String(values.get("api_key") ?? "").trim();
    if (creating) {
      await onSave({
        name: String(values.get("name") ?? "").trim(),
        provider,
        base_url: String(values.get("base_url") ?? "").trim(),
        api_key: apiKey,
        default_models: defaults
      });
      return;
    }
    await onSave({
      name: String(values.get("name") ?? "").trim(),
      provider,
      base_url: String(values.get("base_url") ?? "").trim(),
      ...(apiKey ? { api_key: apiKey } : {}),
      default_models: defaults
    });
  }

  if (!group && !creating) {
    return (
      <section className="key-group-empty-sheet">
        <span className="key-group-paper-label">PROVIDER WALLET</span>
        <strong>{zh ? "从左边挑一张 Key Group。" : "Pick a Key Group from the index."}</strong>
        <p>
          {zh
            ? "这里会显示 Provider、默认模型和能力用途。API Key 始终留在加密 Credential Vault。"
            : "Provider, default models, and capability roles live here. API keys remain in the encrypted Credential Vault."}
        </p>
      </section>
    );
  }

  const editing = Boolean(group);
  return (
    <form
      key={group?.id ?? "new-key-group"}
      className="key-group-detail-sheet"
      onSubmit={submit}
    >
      <header className="key-group-detail-heading">
        <div>
          <span className="key-group-paper-label">
            {editing ? "KEY GROUP FILE" : "NEW KEY GROUP"}
          </span>
          <h3>{editing ? group?.name : zh ? "建立 Provider 钱包" : "File a provider wallet"}</h3>
          <p>
            {editing
              ? zh
                ? "直接修改这里的默认模型。没有 Character override 的 assignment 会继承新默认值。"
                : "Edit default models here. Assignments without a Character override inherit the new defaults."
              : zh
                ? "一组 Provider / API Key 可以分别负责文字、看图和生成图片。"
                : "One Provider/API key can serve text, media understanding, and image generation separately."}
          </p>
        </div>
        {editing && (
          <span className={`key-group-key-stamp${group?.credential_configured ? " is-ready" : ""}`}>
            {group?.credential_configured ? "KEY ✓" : "NO KEY"}
          </span>
        )}
      </header>

      <section className="key-group-provider-note">
        <label>
          <span>{zh ? "名称" : "Name"}</span>
          <input name="name" required defaultValue={group?.name ?? ""} placeholder="My OpenRouter" />
        </label>
        <label>
          <span>Provider</span>
          <select name="provider" defaultValue={group?.provider ?? "openrouter"}>
            {providerOptions.map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="is-wide">
          <span>Base URL</span>
          <input
            name="base_url"
            defaultValue={group?.base_url ?? ""}
            placeholder="Optional for OpenRouter"
          />
        </label>
        <label className="is-wide">
          <span>{editing ? (zh ? "替换 API Key" : "Replace API key") : "API Key"}</span>
          <input
            name="api_key"
            type="password"
            required={!editing}
            autoComplete="off"
            placeholder={
              editing
                ? zh
                  ? "留空 = 保留现有 Key"
                  : "Leave blank to keep the current key"
                : "sk-or-..."
            }
          />
        </label>
      </section>

      <div className="key-group-capability-notes">
        <section className="key-group-capability-note is-lavender">
          <span className="key-group-capability-tag">TXT / CHARACTER</span>
          <strong>{zh ? "角色文字模型" : "Character text model"}</strong>
          <small>{zh ? "聊天、角色思考与 Tool calling。" : "Chat, character reasoning, and Tool calling."}</small>
          <input
            name="character_model"
            defaultValue={group?.default_models.character ?? ""}
            placeholder="deepseek-v4-flash"
          />
        </section>

        <section className="key-group-capability-note is-mint">
          <span className="key-group-capability-tag">EYE / MEDIA</span>
          <strong>{zh ? "媒体理解模型" : "Media understanding model"}</strong>
          <small>{zh ? "角色选择查看图片 / 视频后使用。" : "Used after a character chooses to inspect shared media."}</small>
          <input
            name="media_model"
            defaultValue={group?.default_models.media ?? ""}
            placeholder="xiaomi/mimo-v2.5"
          />
        </section>

        <section className="key-group-capability-note is-rose key-group-image-note">
          <span className="key-group-capability-tag">IMG / CREATE</span>
          <strong>{zh ? "图片生成" : "Image generation"}</strong>
          <small>
            {zh
              ? "可以固定 Model，也可以让 Character Relay 自动寻找真正免费的模型。"
              : "Pin a model, or let Character Relay scout genuinely free image models automatically."}
          </small>

          <div className="key-group-image-mode" role="group" aria-label="Image model mode">
            <button
              type="button"
              className={imageMode === "manual" ? "is-active" : ""}
              onClick={() => setImageMode("manual")}
            >
              {zh ? "手动指定" : "Manual"}
            </button>
            <button
              type="button"
              className={imageMode === "auto" ? "is-active" : ""}
              onClick={() => setImageMode("auto")}
            >
              AUTO · FREE · ANIME FIRST
            </button>
          </div>

          {imageMode === "manual" ? (
            <input
              name="image_generation_model"
              defaultValue={
                savedImageModel === AUTO_FREE_ANIME_MODEL ? "" : savedImageModel
              }
              placeholder="Image model ID"
            />
          ) : (
            <div className="key-group-scout-note">
              <div className="key-group-scout-heading">
                <span>FREE MODEL SCOUT</span>
                {group && group.provider === "openrouter" && (
                  <button
                    type="button"
                    disabled={scouting}
                    onClick={() => void inspectFreeModels(true)}
                  >
                    {scouting ? (zh ? "扫描中…" : "Scanning…") : zh ? "重新扫描" : "Scan now"}
                  </button>
                )}
              </div>
              <p>
                {zh
                  ? "每 6 小时最多重新拉一次目录；运行时缓存过期才懒加载刷新。只接受所有 pricing line 都是 $0 的 endpoint，不会自动 fallback 到付费模型。"
                  : "Catalog results are cached for six hours and refreshed lazily. Only endpoints whose pricing lines are all $0 qualify; there is no automatic paid fallback."}
              </p>
              {!group && (
                <small>{zh ? "先保存 Key Group，之后才能用它的 OpenRouter Key 扫描。" : "Save the Key Group first so its OpenRouter key can run the scout."}</small>
              )}
              {group && group.provider !== "openrouter" && (
                <small>{zh ? "这个自动模式目前只接 OpenRouter。" : "This automatic mode currently supports OpenRouter only."}</small>
              )}
              {scout?.selected_model && (
                <div className="key-group-scout-pick">
                  <span>{zh ? "当前首选" : "CURRENT PICK"}</span>
                  <strong>{scout.candidates[0]?.name ?? scout.selected_model}</strong>
                  <code>{scout.selected_model}</code>
                  <div>
                    <b>FREE</b>
                    <b>ANIME PRIORITY</b>
                    {scout.candidates[0]?.style_matches.slice(0, 3).map((match) => (
                      <i key={match}>#{match}</i>
                    ))}
                  </div>
                </div>
              )}
              {scout && scout.candidates.length > 1 && (
                <div className="key-group-scout-candidates">
                  {scout.candidates.slice(1, 4).map((candidate) => (
                    <span key={candidate.model_id}>
                      <strong>{candidate.name}</strong>
                      <small>{candidate.style_matches.slice(0, 2).join(" · ") || "free fallback"}</small>
                    </span>
                  ))}
                </div>
              )}
              {scout && (
                <small>
                  {zh ? "检查" : "Checked"} {scout.total_image_models} {zh ? "个图片模型" : "image models"}
                  {scout.from_cache ? (zh ? " · 使用缓存" : " · cached") : ""}
                  {` · ${new Date(scout.checked_at).toLocaleString()}`}
                </small>
              )}
              {scoutMessage && <p className="key-group-scout-warning">{scoutMessage}</p>}
            </div>
          )}
        </section>
      </div>

      <footer className="key-group-detail-actions">
        {creating && (
          <button type="button" className="paper-button" onClick={onCancelCreate}>
            {zh ? "取消" : "Cancel"}
          </button>
        )}
        <button className="ink-button" disabled={working}>
          {working
            ? zh
              ? "保存中…"
              : "Saving…"
            : creating
              ? zh
                ? "建立 Key Group"
                : "Create Key Group"
              : zh
                ? "保存修改"
                : "Save changes"}
        </button>
      </footer>
    </form>
  );
}

export function KeyGroupsPanel() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [groups, setGroups] = useState<ProviderKeyGroup[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [creating, setCreating] = useState(false);
  const [selectedCards, setSelectedCards] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<KeyGroupCapability[]>(["media"]);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selectedGroup = useMemo(
    () => groups.find((item) => item.id === selectedGroupId) ?? null,
    [groups, selectedGroupId]
  );

  useEffect(() => {
    void load();
  }, []);

  async function load(preferredGroupId?: string) {
    try {
      const [nextGroups, nextCharacters] = await Promise.all([
        keyGroupApi.list(),
        api.listCharacters()
      ]);
      setGroups(nextGroups);
      setCharacters(nextCharacters);
      setSelectedGroupId((current) => {
        const preferred = preferredGroupId || current;
        return nextGroups.some((item) => item.id === preferred)
          ? preferred
          : nextGroups[0]?.id ?? "";
      });
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function run(action: () => Promise<void>) {
    try {
      setWorking(true);
      setMessage(null);
      await action();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function saveGroup(payload: ProviderKeyGroupCreate | ProviderKeyGroupUpdate) {
    await run(async () => {
      if (creating) {
        const created = await keyGroupApi.create(payload as ProviderKeyGroupCreate);
        setCreating(false);
        await load(created.id);
        setMessage(zh ? "Key Group 已建立。" : "Key Group created.");
        return;
      }
      if (!selectedGroup) return;
      const updated = await keyGroupApi.update(
        selectedGroup.id,
        payload as ProviderKeyGroupUpdate
      );
      await load(updated.id);
      setMessage(
        zh
          ? "Key Group 已更新；没有 model override 的角色会继承新的默认模型。"
          : "Key Group updated. Characters without a model override inherit the new defaults."
      );
    });
  }

  function toggleCard(cardId: string) {
    setSelectedCards((current) =>
      current.includes(cardId)
        ? current.filter((item) => item !== cardId)
        : [...current, cardId]
    );
  }

  function toggleCapability(capability: KeyGroupCapability) {
    setCapabilities((current) =>
      current.includes(capability)
        ? current.filter((item) => item !== capability)
        : [...current, capability]
    );
  }

  async function applySelected() {
    if (!selectedGroup || !selectedCards.length || !capabilities.length) return;
    await run(async () => {
      const result = await keyGroupApi.bulkApply(selectedGroup.id, {
        character_card_ids: selectedCards,
        capabilities
      });
      setMessage(
        zh
          ? `已套用 ${result.applied} 个 capability assignment。`
          : `Applied ${result.applied} capability assignments.`
      );
    });
  }

  async function removeGroup(group: ProviderKeyGroup) {
    const confirmed = window.confirm(
      zh
        ? `删除「${group.name}」？使用它的 capability assignment 会一起失效。`
        : `Delete “${group.name}”? Capability assignments using it will stop resolving.`
    );
    if (!confirmed) return;
    await run(async () => {
      await keyGroupApi.remove(group.id);
      if (selectedGroupId === group.id) setSelectedGroupId("");
      await load();
      setMessage(zh ? "Key Group 已删除。" : "Key Group deleted.");
    });
  }

  return (
    <article className="key-groups-notebook" style={{ gridColumn: "1 / -1" }}>
      <header className="key-groups-title-note">
        <span className="portal-v2-tape">PROVIDER WALLET</span>
        <div>
          <h3>{zh ? "Key Groups / 能力钱包" : "Key Groups / capability wallet"}</h3>
          <p>
            {zh
              ? "Key 只保存一次；文字、媒体理解和图片生成各自选模型，再把整组能力贴到角色卡上。"
              : "Store a key once, choose separate models for text, media, and image generation, then attach those capabilities to Character Cards."}
          </p>
        </div>
      </header>

      {message && <p className="error-note key-groups-message">{message}</p>}

      <div className="key-groups-workspace">
        <aside className="key-group-index-note">
          <div className="key-group-index-heading">
            <span>{zh ? "钱包索引" : "KEY GROUP INDEX"}</span>
            <strong>{groups.length}</strong>
          </div>
          <div className="key-group-index-list">
            {groups.map((group, index) => {
              const modelCaps = (Object.keys(capabilityLabels) as KeyGroupCapability[]).filter(
                (capability) => Boolean(group.default_models[capability])
              );
              return (
                <button
                  type="button"
                  className={`key-group-index-card${
                    !creating && selectedGroupId === group.id ? " is-active" : ""
                  }`}
                  onClick={() => {
                    setCreating(false);
                    setSelectedGroupId(group.id);
                  }}
                  key={group.id}
                >
                  <small>FILE / {String(index + 1).padStart(2, "0")}</small>
                  <strong>{group.name}</strong>
                  <span>{group.provider}</span>
                  <div>
                    {modelCaps.map((capability) => (
                      <i key={capability}>{capabilityMarks[capability]}</i>
                    ))}
                    <b className={group.credential_configured ? "is-ready" : ""}>
                      {group.credential_configured ? "KEY ✓" : "NO KEY"}
                    </b>
                  </div>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className={`key-group-new-note${creating ? " is-active" : ""}`}
            onClick={() => {
              setCreating(true);
              setSelectedGroupId("");
            }}
          >
            <span>＋</span>
            <strong>{zh ? "新建 Key Group" : "New Key Group"}</strong>
          </button>
        </aside>

        <KeyGroupEditor
          group={selectedGroup}
          creating={creating}
          working={working}
          zh={zh}
          onSave={saveGroup}
          onCancelCreate={() => {
            setCreating(false);
            setSelectedGroupId(groups[0]?.id ?? "");
          }}
        />

        <aside className="key-group-apply-note">
          <span className="key-group-paper-label">APPLY NOTE</span>
          <h4>{zh ? "把能力贴给角色" : "Attach capabilities"}</h4>
          {selectedGroup ? (
            <>
              <p>
                <strong>{selectedGroup.name}</strong>
                <small>{selectedGroup.provider}</small>
              </p>
              <div className="key-group-apply-capabilities">
                {(Object.keys(capabilityLabels) as KeyGroupCapability[]).map((capability) => (
                  <label key={capability}>
                    <input
                      type="checkbox"
                      checked={capabilities.includes(capability)}
                      onChange={() => toggleCapability(capability)}
                    />
                    <span>{capabilityMarks[capability]}</span>
                    {capabilityLabels[capability]}
                  </label>
                ))}
              </div>

              <div className="key-group-character-heading">
                <span>{zh ? "角色卡" : "CHARACTER FILES"}</span>
                <button
                  type="button"
                  onClick={() =>
                    setSelectedCards(
                      selectedCards.length === characters.length
                        ? []
                        : characters.map((card) => card.id)
                    )
                  }
                >
                  {selectedCards.length === characters.length
                    ? zh ? "清空" : "Clear"
                    : zh ? "全选" : "All"}
                </button>
              </div>
              <div className="key-group-character-list">
                {characters.map((card) => (
                  <label key={card.id}>
                    <input
                      type="checkbox"
                      checked={selectedCards.includes(card.id)}
                      onChange={() => toggleCard(card.id)}
                    />
                    <span>
                      <strong>{card.display_name}</strong>
                      <small>{card.subtitle}</small>
                    </span>
                  </label>
                ))}
              </div>
              <button
                type="button"
                className="ink-button key-group-apply-button"
                disabled={
                  working || selectedCards.length === 0 || capabilities.length === 0
                }
                onClick={() => void applySelected()}
              >
                {zh
                  ? `套用到 ${selectedCards.length} 张角色卡`
                  : `Apply to ${selectedCards.length} Character Cards`}
              </button>
              <small className="key-group-apply-footnote">
                {zh
                  ? "Bulk Apply 不会复制 API Key；只建立角色卡到 Key Group 的 capability assignment。"
                  : "Bulk Apply never copies the API key; it only creates Character-to-Key-Group capability assignments."}
              </small>
              <button
                type="button"
                className="key-group-delete-link"
                disabled={working}
                onClick={() => void removeGroup(selectedGroup)}
              >
                {zh ? "删除这个 Key Group" : "Delete this Key Group"}
              </button>
            </>
          ) : (
            <p>
              {zh
                ? "先从左边选一张 Key Group，再决定哪些角色共享它。"
                : "Select a Key Group first, then choose which characters share it."}
            </p>
          )}
        </aside>
      </div>
    </article>
  );
}
