import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, type CharacterCard } from "./api";
import { useI18n } from "./i18n";
import {
  keyGroupApi,
  type KeyGroupCapability,
  type ProviderKeyGroup
} from "./keyGroupApi";

const capabilityLabels: Record<KeyGroupCapability, string> = {
  character: "Character / Text",
  media: "Media Understanding",
  image_generation: "Image Generation"
};

const capabilityOrder: KeyGroupCapability[] = [
  "character",
  "media",
  "image_generation"
];

function defaultModels(values: FormData): Partial<Record<KeyGroupCapability, string>> {
  const defaults: Partial<Record<KeyGroupCapability, string>> = {};
  for (const capability of capabilityOrder) {
    const value = String(values.get(`${capability}_model`) ?? "").trim();
    if (value) defaults[capability] = value;
  }
  return defaults;
}

export function KeyGroupsPanel() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [groups, setGroups] = useState<ProviderKeyGroup[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [selectedCards, setSelectedCards] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<KeyGroupCapability[]>(["media"]);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selectedGroup = useMemo(
    () => groups.find((item) => item.id === selectedGroupId) ?? null,
    [groups, selectedGroupId]
  );
  const editingGroup = useMemo(
    () => groups.find((item) => item.id === editingGroupId) ?? null,
    [groups, editingGroupId]
  );

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [nextGroups, nextCharacters] = await Promise.all([
        keyGroupApi.list(),
        api.listCharacters()
      ]);
      setGroups(nextGroups);
      setCharacters(nextCharacters);
      setSelectedGroupId((current) =>
        nextGroups.some((item) => item.id === current) ? current : nextGroups[0]?.id || ""
      );
      setEditingGroupId((current) =>
        current && nextGroups.some((item) => item.id === current) ? current : null
      );
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

  async function createGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await run(async () => {
      const created = await keyGroupApi.create({
        name: String(values.get("name") ?? "").trim(),
        provider: String(values.get("provider") ?? "").trim(),
        base_url: String(values.get("base_url") ?? "").trim(),
        api_key: String(values.get("api_key") ?? ""),
        default_models: defaultModels(values)
      });
      form.reset();
      await load();
      setSelectedGroupId(created.id);
      setMessage(zh ? "Key Group 已建立。" : "Key Group created.");
    });
  }

  async function updateGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingGroup) return;
    const values = new FormData(event.currentTarget);
    const replacementKey = String(values.get("api_key") ?? "").trim();
    await run(async () => {
      await keyGroupApi.update(editingGroup.id, {
        name: String(values.get("name") ?? "").trim(),
        provider: String(values.get("provider") ?? "").trim(),
        base_url: String(values.get("base_url") ?? "").trim(),
        ...(replacementKey ? { api_key: replacementKey } : {}),
        default_models: defaultModels(values)
      });
      await load();
      setEditingGroupId(null);
      setMessage(
        zh
          ? "Key Group 已更新。未设置 Model Override 的角色会自动使用新的默认模型。"
          : "Key Group updated. Assignments without a model override now use the new defaults."
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
    if (!selectedGroupId || !selectedCards.length || !capabilities.length) return;
    await run(async () => {
      const result = await keyGroupApi.bulkApply(selectedGroupId, {
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

  return (
    <article className="account-action-card" style={{ gridColumn: "1 / -1" }}>
      <h3>{zh ? "Key Groups / 共用 API 凭证" : "Key Groups / shared API credentials"}</h3>
      <p>
        {zh
          ? "每个账号保存一次 Provider/API Key，再按 Character、Media、Image capability 批量套用到多张角色卡。API Key 不会从接口回传明文。"
          : "Store a provider/API key once per account, then bulk-apply it to Character, Media, or Image capabilities. Plaintext API keys are never returned."}
      </p>

      {message && <p className="error-note">{message}</p>}

      <form className="compact-form" onSubmit={createGroup}>
        <label>
          {zh ? "名称" : "Name"}
          <input name="name" required placeholder="My OpenRouter" />
        </label>
        <label>
          Provider
          <select name="provider" defaultValue="openrouter">
            <option value="openrouter">OpenRouter</option>
            <option value="openai">OpenAI-compatible</option>
            <option value="deepseek">DeepSeek</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label>
          Base URL
          <input name="base_url" placeholder="Optional for OpenRouter" />
        </label>
        <label>
          API Key
          <input name="api_key" type="password" required autoComplete="off" />
        </label>
        <label>
          Character model
          <input name="character_model" placeholder="deepseek-v4-flash" />
        </label>
        <label>
          Media model
          <input name="media_model" placeholder="xiaomi/mimo-v2.5" />
        </label>
        <label>
          Image model
          <input name="image_generation_model" placeholder="Optional" />
        </label>
        <button className="paper-button" disabled={working}>
          {zh ? "建立 Key Group" : "Create Key Group"}
        </button>
      </form>

      <div className="compact-list" style={{ marginTop: 16 }}>
        {groups.length === 0 && <p>{zh ? "尚未建立 Key Group。" : "No Key Groups yet."}</p>}
        {groups.map((group) => {
          const modelSummary = capabilityOrder
            .map((capability) => {
              const model = group.default_models[capability];
              return model ? `${capabilityLabels[capability]}: ${model}` : "";
            })
            .filter(Boolean)
            .join(" · ");
          return (
            <div key={group.id}>
              <span>
                <strong>{group.name}</strong>
                <small>
                  {group.provider}
                  {modelSummary ? ` · ${modelSummary}` : ""}
                </small>
              </span>
              <span className={`status-chip${group.credential_configured ? " pass" : ""}`}>
                {group.credential_configured ? "key ✓" : "no key"}
              </span>
              <button
                type="button"
                className="paper-button"
                disabled={working}
                onClick={() => setEditingGroupId(group.id)}
              >
                {zh ? "编辑" : "Edit"}
              </button>
              <button
                type="button"
                disabled={working}
                onClick={() =>
                  void run(async () => {
                    await keyGroupApi.remove(group.id);
                    if (selectedGroupId === group.id) setSelectedGroupId("");
                    if (editingGroupId === group.id) setEditingGroupId(null);
                    await load();
                  })
                }
                aria-label={zh ? "删除 Key Group" : "Delete Key Group"}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>

      {editingGroup && (
        <section className="account-action-card" style={{ marginTop: 18 }}>
          <h3>{zh ? `编辑 ${editingGroup.name}` : `Edit ${editingGroup.name}`}</h3>
          <p>
            {zh
              ? "可以直接更换默认模型。已有 assignment 如果没有单独设置 Model Override，会立即继承这里的新模型。API Key 留空会保留原本的 Key。"
              : "Change default models here. Existing assignments without a Model Override inherit the new model immediately. Leave API Key blank to keep the current key."}
          </p>
          <form key={editingGroup.id} className="compact-form" onSubmit={updateGroup}>
            <label>
              {zh ? "名称" : "Name"}
              <input name="name" required defaultValue={editingGroup.name} />
            </label>
            <label>
              Provider
              <select name="provider" defaultValue={editingGroup.provider}>
                <option value="openrouter">OpenRouter</option>
                <option value="openai">OpenAI-compatible</option>
                <option value="deepseek">DeepSeek</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label>
              Base URL
              <input name="base_url" defaultValue={editingGroup.base_url} />
            </label>
            <label>
              {zh ? "替换 API Key（可选）" : "Replace API Key (optional)"}
              <input
                name="api_key"
                type="password"
                autoComplete="off"
                placeholder={zh ? "留空保留现有 Key" : "Leave blank to keep current key"}
              />
            </label>
            <label>
              Character model
              <input
                name="character_model"
                defaultValue={editingGroup.default_models.character ?? ""}
                placeholder="deepseek-v4-flash"
              />
            </label>
            <label>
              Media model
              <input
                name="media_model"
                defaultValue={editingGroup.default_models.media ?? ""}
                placeholder="xiaomi/mimo-v2.5"
              />
            </label>
            <label>
              Image model
              <input
                name="image_generation_model"
                defaultValue={editingGroup.default_models.image_generation ?? ""}
                placeholder="Optional"
              />
            </label>
            <div style={{ display: "flex", gap: 8, alignItems: "end" }}>
              <button className="paper-button" disabled={working}>
                {zh ? "保存修改" : "Save changes"}
              </button>
              <button
                type="button"
                className="paper-button"
                disabled={working}
                onClick={() => setEditingGroupId(null)}
              >
                {zh ? "取消" : "Cancel"}
              </button>
            </div>
          </form>
        </section>
      )}

      {groups.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3>{zh ? "批量套用" : "Bulk apply"}</h3>
          <label>
            Key Group
            <select
              value={selectedGroupId}
              onChange={(event) => setSelectedGroupId(event.target.value)}
            >
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name} · {group.provider}
                </option>
              ))}
            </select>
          </label>
          {selectedGroup && (
            <p>
              {zh ? "默认模型" : "Defaults"}: {JSON.stringify(selectedGroup.default_models)}
            </p>
          )}

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "12px 0" }}>
            {(Object.keys(capabilityLabels) as KeyGroupCapability[]).map((capability) => (
              <label key={capability} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={capabilities.includes(capability)}
                  onChange={() => toggleCapability(capability)}
                />
                {capabilityLabels[capability]}
              </label>
            ))}
          </div>

          <div className="compact-list">
            {characters.map((card) => (
              <label key={card.id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
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
            className="paper-button"
            disabled={
              working ||
              !selectedGroupId ||
              selectedCards.length === 0 ||
              capabilities.length === 0
            }
            onClick={() => void applySelected()}
            style={{ marginTop: 12 }}
          >
            {zh
              ? `套用到 ${selectedCards.length} 张角色卡`
              : `Apply to ${selectedCards.length} Character Cards`}
          </button>
        </div>
      )}
    </article>
  );
}
