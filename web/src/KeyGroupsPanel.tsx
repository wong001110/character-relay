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

export function KeyGroupsPanel() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [groups, setGroups] = useState<ProviderKeyGroup[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
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

  async function load() {
    try {
      const [nextGroups, nextCharacters] = await Promise.all([
        keyGroupApi.list(),
        api.listCharacters()
      ]);
      setGroups(nextGroups);
      setCharacters(nextCharacters);
      setSelectedGroupId((current) => current || nextGroups[0]?.id || "");
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
    const defaults: Partial<Record<KeyGroupCapability, string>> = {};
    for (const capability of [
      "character",
      "media",
      "image_generation"
    ] as KeyGroupCapability[]) {
      const value = String(values.get(`${capability}_model`) ?? "").trim();
      if (value) defaults[capability] = value;
    }
    await run(async () => {
      const created = await keyGroupApi.create({
        name: String(values.get("name") ?? "").trim(),
        provider: String(values.get("provider") ?? "").trim(),
        base_url: String(values.get("base_url") ?? "").trim(),
        api_key: String(values.get("api_key") ?? ""),
        default_models: defaults
      });
      form.reset();
      await load();
      setSelectedGroupId(created.id);
      setMessage(zh ? "Key Group 已建立。" : "Key Group created.");
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
        {groups.map((group) => (
          <div key={group.id}>
            <span>
              <strong>{group.name}</strong>
              <small>
                {group.provider}
                {group.default_models.media
                  ? ` · media: ${group.default_models.media}`
                  : ""}
              </small>
            </span>
            <span className={`status-chip${group.credential_configured ? " pass" : ""}`}>
              {group.credential_configured ? "key ✓" : "no key"}
            </span>
            <button
              type="button"
              disabled={working}
              onClick={() =>
                void run(async () => {
                  await keyGroupApi.remove(group.id);
                  if (selectedGroupId === group.id) setSelectedGroupId("");
                  await load();
                })
              }
              aria-label={zh ? "删除 Key Group" : "Delete Key Group"}
            >
              ×
            </button>
          </div>
        ))}
      </div>

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
