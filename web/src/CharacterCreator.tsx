import { useMemo, useRef, useState, type FormEvent } from "react";

import {
  api,
  type CharacterCard,
  type CharacterCardCreate,
  type CharacterCardUpdate,
  type PromptCharacterCreate,
  type ProviderId,
  type TargetView,
  type TestKind
} from "./api";
import { useI18n } from "./i18n";
import {
  NotebookField,
  NotebookInput,
  NotebookSection,
  NotebookSelect,
  NotebookTextarea,
  PaperDrawer
} from "./NotebookUI";
import { getProviderPreset, providerPresets } from "./providerPresets";

interface Props {
  targets: TargetView[];
  card?: CharacterCard | null;
  target?: TargetView | null;
  onClose: () => void;
  onSaved: (card: CharacterCard) => void;
}

type BindingMode = "prompt" | "existing";

const allSuites: TestKind[] = [
  "identity_integrity",
  "false_memory",
  "prompt_injection",
  "long_conversation_drift"
];

const providerNoteKeys = {
  deepseek: "provider.note.deepseek",
  openai: "provider.note.openai",
  openrouter: "provider.note.openrouter",
  custom: "provider.note.custom"
} as const;

function splitList(value: string): string[] {
  return value
    .split(/[,，\n]/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

function configString(target: TargetView | null | undefined, key: string): string {
  const value = target?.config[key];
  return typeof value === "string" ? value : "";
}

function configNumber(
  target: TargetView | null | undefined,
  key: string,
  fallback: number
): number {
  const value = target?.config[key];
  return typeof value === "number" ? value : fallback;
}

function commonFields(data: FormData): Omit<CharacterCardCreate, "target_id"> {
  return {
    display_name: String(data.get("display_name")),
    subtitle: String(data.get("subtitle")),
    subject_type: String(data.get("subject_type")) as CharacterCard["subject_type"],
    persona_summary: String(data.get("persona_summary")),
    traits: splitList(String(data.get("traits"))),
    tags: splitList(String(data.get("tags"))),
    expected_tone: String(data.get("expected_tone")) || null,
    forbidden_behaviors: splitList(String(data.get("forbidden_behaviors"))),
    memory_summary: String(data.get("memory_summary")) || null,
    preferred_suites: allSuites,
    portrait_variant: String(data.get("portrait_variant")) as CharacterCard["portrait_variant"]
  };
}

export function CharacterCreator({
  targets,
  card = null,
  target = null,
  onClose,
  onSaved
}: Props) {
  const { t, language } = useI18n();
  const zh = language === "zh-CN";
  const editing = Boolean(card);
  const userTargets = useMemo(
    () => targets.filter((item) => !item.id.startsWith("demo-")),
    [targets]
  );
  const initialPreset = useMemo(() => getProviderPreset("deepseek"), []);
  const initialBinding: BindingMode = target?.target_kind === "prompt_model" ? "prompt" : "existing";
  const initialProvider = (configString(target, "provider") || "deepseek") as ProviderId;
  const [bindingMode, setBindingMode] = useState<BindingMode>(
    editing ? initialBinding : "prompt"
  );
  const [provider, setProvider] = useState<ProviderId>(initialProvider);
  const [baseUrl, setBaseUrl] = useState(
    configString(target, "base_url") || initialPreset.baseUrl
  );
  const [model, setModel] = useState(
    configString(target, "model") || initialPreset.defaultModel
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(!editing);
  const [assistantBrief, setAssistantBrief] = useState("");
  const [assistantRelationship, setAssistantRelationship] = useState("");
  const [assistantConstraints, setAssistantConstraints] = useState("");
  const [assistantWorking, setAssistantWorking] = useState(false);
  const [assistantMessage, setAssistantMessage] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  function setFormValue(name: string, value: string) {
    const element = formRef.current?.elements.namedItem(name);
    if (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      element instanceof HTMLSelectElement
    ) {
      element.value = value;
    }
  }

  async function generateCharacterDraft() {
    const concept = assistantBrief.trim();
    if (concept.length < 10) {
      setAssistantMessage(
        zh ? "先用至少十个字描述角色定位与核心想法。" : "Describe the character concept in at least ten characters."
      );
      return;
    }
    try {
      setAssistantWorking(true);
      setAssistantMessage(null);
      const suggestion = await api.suggestCharacter({
        concept,
        name_hint: String(
          (formRef.current?.elements.namedItem("display_name") as HTMLInputElement | null)
            ?.value ?? ""
        ),
        relationship_context: assistantRelationship.trim(),
        writing_constraints: assistantConstraints.trim(),
        subject_type_hint: String(
          (formRef.current?.elements.namedItem("subject_type") as HTMLSelectElement | null)
            ?.value ?? "custom"
        ) as CharacterCard["subject_type"],
        language: zh ? "zh-CN" : "en"
      });
      setFormValue("display_name", suggestion.display_name);
      setFormValue("subtitle", suggestion.subtitle);
      setFormValue("subject_type", suggestion.subject_type);
      setFormValue("persona_summary", suggestion.persona_summary);
      setFormValue("traits", suggestion.traits.join("\n"));
      setFormValue("tags", suggestion.tags.join("\n"));
      setFormValue("expected_tone", suggestion.expected_tone);
      setFormValue("forbidden_behaviors", suggestion.forbidden_behaviors.join("\n"));
      setFormValue("memory_summary", suggestion.memory_summary);
      if (promptFields) setFormValue("system_prompt", suggestion.system_prompt);
      setAssistantMessage(
        zh
          ? `已使用 ${suggestion.provider_model} 填入角色草稿。请逐区审核后再保存。`
          : `Drafted with ${suggestion.provider_model}. Review every section before saving.`
      );
    } catch (reason) {
      setAssistantMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAssistantWorking(false);
    }
  }

  function changeProvider(nextProvider: ProviderId) {
    const preset = getProviderPreset(nextProvider);
    setProvider(nextProvider);
    setBaseUrl(preset.baseUrl);
    setModel(preset.defaultModel);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const common = commonFields(data);

    try {
      setSaving(true);
      setMessage(null);
      if (editing && card) {
        const payload: CharacterCardUpdate = {
          ...common,
          ...(target?.target_kind === "prompt_model"
            ? {
                provider,
                base_url: baseUrl,
                model,
                system_prompt: String(data.get("system_prompt")),
                temperature: Number(data.get("temperature"))
              }
            : {})
        };
        onSaved(await api.updateCharacter(card.id, payload));
      } else if (bindingMode === "prompt") {
        const payload: PromptCharacterCreate = {
          ...common,
          provider,
          base_url: baseUrl,
          model,
          system_prompt: String(data.get("system_prompt")),
          temperature: Number(data.get("temperature")),
          api_key: String(data.get("api_key"))
        };
        onSaved(await api.createPromptCharacter(payload));
      } else {
        const payload: CharacterCardCreate = {
          ...common,
          target_id: String(data.get("target_id"))
        };
        onSaved(await api.createCharacter(payload));
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("creator.error"));
    } finally {
      setSaving(false);
    }
  }

  const promptFields = bindingMode === "prompt" || target?.target_kind === "prompt_model";

  return (
    <PaperDrawer
      onClose={onClose}
      ariaLabel={editing ? t("creator.editHeading") : t("creator.heading")}
      className="character-editor-drawer"
    >
      <form ref={formRef} className="notebook-form-paper" onSubmit={submit}>
        <header className="notebook-form-intro">
          <p className="tape-label">
            {editing ? t("creator.editLabel") : t("creator.label")}
          </p>
          <h2>{editing ? t("creator.editHeading") : t("creator.heading")}</h2>
          <p>
            {zh
              ? "把角色当成一页持续补充的手帐：先写清楚他是谁，再写他说话的方式、边界与记忆。每一区都附有填写方向。"
              : "Treat this as a living character notebook: define who they are, then document their voice, boundaries, and memory. Each section includes a writing guide."}
          </p>
        </header>

        <section className={`character-ai-drafter${assistantOpen ? " is-open" : ""}`}>
          <button
            className="character-ai-drafter-toggle"
            type="button"
            onClick={() => setAssistantOpen((current) => !current)}
            aria-expanded={assistantOpen}
          >
            <span className="toolbox-sticker sticker-lavender">AI DRAFT</span>
            <span>
              <strong>{zh ? "让 AI 帮你起草角色卡" : "Draft the Character Card with AI"}</strong>
              <small>
                {zh
                  ? "描述一次，回填 Persona、Traits、Tone、边界、记忆与 System Prompt。"
                  : "Describe once, then review Persona, Traits, Tone, boundaries, memory, and System Prompt."}
              </small>
            </span>
            <b aria-hidden="true">{assistantOpen ? "−" : "+"}</b>
          </button>
          {assistantOpen && (
            <div className="character-ai-drafter-body">
              <NotebookField
                className="is-wide"
                label={zh ? "角色概念与核心定位" : "Character concept and core positioning"}
                guide={zh ? "写身份、性格方向、主要关系、世界观或用途。" : "Describe identity, personality direction, relationships, world, or purpose."}
                required
              >
                <NotebookTextarea
                  rows={5}
                  value={assistantBrief}
                  onChange={(event) => setAssistantBrief(event.currentTarget.value)}
                  placeholder={
                    zh
                      ? "例如：一位擅长把混乱需求整理成产品路线图的 AI 产品制作人，务实、好奇，但容易同时开太多项目。"
                      : "Example: an AI product producer who turns vague ideas into executable roadmaps; practical and curious, but prone to starting too many projects."
                  }
                />
              </NotebookField>
              <NotebookField label={zh ? "关系与互动背景" : "Relationship and interaction context"}>
                <NotebookTextarea
                  rows={3}
                  value={assistantRelationship}
                  onChange={(event) => setAssistantRelationship(event.currentTarget.value)}
                  placeholder={zh ? "角色与用户或其他角色是什么关系？" : "How does the character relate to the user or other characters?"}
                />
              </NotebookField>
              <NotebookField label={zh ? "额外限制" : "Additional constraints"}>
                <NotebookTextarea
                  rows={3}
                  value={assistantConstraints}
                  onChange={(event) => setAssistantConstraints(event.currentTarget.value)}
                  placeholder={zh ? "不要使用的语气、必须保留的设定、语言偏好等。" : "Voice to avoid, required canon, language preferences, and other constraints."}
                />
              </NotebookField>
              <div className="character-ai-drafter-actions">
                <button
                  className="ink-button"
                  type="button"
                  onClick={() => void generateCharacterDraft()}
                  disabled={assistantWorking || saving}
                >
                  {assistantWorking
                    ? zh
                      ? "生成中…"
                      : "Generating…"
                    : zh
                      ? "生成并填入草稿"
                      : "Generate and fill draft"}
                </button>
                <small>
                  {zh
                    ? "AI 不会自动保存，也不会改动 API Key 或 Provider 设置。"
                    : "AI never saves automatically and does not change Provider credentials."}
                </small>
              </div>
              {assistantMessage && <p className="character-ai-drafter-message">{assistantMessage}</p>}
            </div>
          )}
        </section>

        {!editing && (
          <div className="binding-tabs notebook-binding-tabs" aria-label={t("creator.bindingAria")}>
            <button
              type="button"
              className={bindingMode === "prompt" ? "selected" : ""}
              onClick={() => setBindingMode("prompt")}
            >
              {t("creator.promptMode")}
              <small>{t("creator.promptModeHelp")}</small>
            </button>
            <button
              type="button"
              className={bindingMode === "existing" ? "selected" : ""}
              onClick={() => setBindingMode("existing")}
              disabled={userTargets.length === 0}
            >
              {t("creator.existingMode")}
              <small>{t("creator.existingModeHelp")}</small>
            </button>
          </div>
        )}

        <NotebookSection
          label="01 / IDENTITY"
          title={zh ? "角色名片" : "Character identity"}
          guide={
            zh
              ? "先让别人能在十秒内理解这个角色是谁。名称用于显示，副标题负责一句话定位。"
              : "Make the character understandable in ten seconds. The name is displayed publicly; the subtitle gives the one-line positioning."
          }
        >
          <NotebookField
            label={t("creator.displayName")}
            guide={zh ? "角色在列表、Discord 与测试房中显示的名称。" : "Shown in the shelf, Discord, and test rooms."}
            required
          >
            <NotebookInput
              name="display_name"
              required
              defaultValue={card?.display_name ?? ""}
              placeholder={t("creator.displayNamePlaceholder")}
            />
          </NotebookField>
          <NotebookField
            label={t("creator.subtitle")}
            guide={zh ? "一句话说明身份、关系或主要用途，不需要写完整背景。" : "A short role, relationship, or purpose—not the full backstory."}
          >
            <NotebookInput
              name="subtitle"
              defaultValue={card?.subtitle ?? ""}
              placeholder={t("creator.subtitlePlaceholder")}
            />
          </NotebookField>
          <NotebookField
            label={t("creator.subjectType")}
            guide={zh ? "用于角色库筛选，不会直接改变 Prompt。" : "Used for shelf filtering; it does not directly change the prompt."}
          >
            <NotebookSelect name="subject_type" defaultValue={card?.subject_type ?? "custom"}>
              <option value="companion">{t("subject.companion")}</option>
              <option value="npc">{t("subject.npc")}</option>
              <option value="assistant">{t("subject.assistant")}</option>
              <option value="custom">{t("subject.custom")}</option>
            </NotebookSelect>
          </NotebookField>
          <NotebookField
            label={t("creator.portraitPalette")}
            guide={zh ? "选择角色卡的便签色调。" : "Choose the note-card palette."}
          >
            <NotebookSelect
              name="portrait_variant"
              defaultValue={card?.portrait_variant ?? "lavender"}
            >
              <option value="lavender">{t("palette.lavender")}</option>
              <option value="rose">{t("palette.rose")}</option>
              <option value="mint">{t("palette.mint")}</option>
              <option value="night">{t("palette.night")}</option>
            </NotebookSelect>
          </NotebookField>
        </NotebookSection>

        <NotebookSection
          label="02 / RUNTIME"
          title={zh ? "AI 连接" : "AI connection"}
          guide={
            zh
              ? "这里决定角色由哪个模型运行。API Key 只在创建请求中使用，不会显示在角色卡内容里。"
              : "Choose which model runs the character. API keys are used for creation and are not displayed as character content."
          }
          accent="mint"
        >
          {promptFields ? (
            <>
              <NotebookField label={t("creator.provider")} guide={t(providerNoteKeys[provider])}>
                <NotebookSelect
                  value={provider}
                  onChange={(event) => changeProvider(event.currentTarget.value as ProviderId)}
                >
                  {providerPresets.map((item) => (
                    <option value={item.id} key={item.id}>{item.label}</option>
                  ))}
                </NotebookSelect>
              </NotebookField>
              <NotebookField label={t("creator.modelId")} guide={zh ? "填写 Provider 实际接受的 Model ID。" : "Use the exact model ID accepted by the provider."} required>
                <NotebookInput
                  value={model}
                  onChange={(event) => setModel(event.currentTarget.value)}
                  required
                  placeholder={t("creator.modelPlaceholder")}
                />
              </NotebookField>
              <NotebookField className="is-wide" label={t("creator.baseUrl")} guide={zh ? "通常保留 Provider 预设；自建兼容 API 时再修改。" : "Keep the preset unless you use a compatible custom endpoint."} required>
                <NotebookInput
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.currentTarget.value)}
                  required
                  placeholder={t("creator.baseUrlPlaceholder")}
                />
              </NotebookField>
              {!editing && (
                <NotebookField className="is-wide" label={t("creator.apiKey")} guide={t("creator.keysNeverSaved")} required>
                  <NotebookInput
                    name="api_key"
                    type="password"
                    required
                    autoComplete="off"
                    placeholder={t("creator.apiKeyPlaceholder")}
                  />
                </NotebookField>
              )}
              <NotebookField
                className="is-wide"
                label={t("creator.systemPrompt")}
                guide={
                  zh
                    ? "写角色必须长期遵守的身份、世界观、表达方式与优先级。不要只写几句形容词，建议使用清晰段落。"
                    : "Document persistent identity, worldview, voice, and priorities. Use clear paragraphs rather than a few adjectives."
                }
                required
              >
                <NotebookTextarea
                  name="system_prompt"
                  rows={14}
                  required
                  defaultValue={configString(target, "system_prompt")}
                  placeholder={t("creator.systemPromptPlaceholder")}
                />
              </NotebookField>
              <NotebookField label={t("creator.temperature")} guide={zh ? "较低更稳定，较高更有变化。" : "Lower is steadier; higher is more varied."} required>
                <NotebookInput
                  name="temperature"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  defaultValue={configNumber(target, "temperature", 0.7)}
                  required
                />
              </NotebookField>
            </>
          ) : (
            <NotebookField className="is-wide" label={t("creator.targetBinding")} guide={zh ? "复用已经建立的 Runtime Target。" : "Reuse an existing runtime target."} required>
              {editing ? (
                <NotebookInput value={target?.name ?? card?.target_id ?? ""} disabled />
              ) : (
                <NotebookSelect name="target_id" required defaultValue={userTargets[0]?.id}>
                  {userTargets.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name} · {item.target_kind}
                    </option>
                  ))}
                </NotebookSelect>
              )}
            </NotebookField>
          )}
        </NotebookSection>

        <NotebookSection
          label="03 / PERSONA"
          title={zh ? "人物核心" : "Persona core"}
          guide={
            zh
              ? "这一区回答：他通常如何看待世界、如何做决定、在关系中是什么样的人。"
              : "Explain how the character sees the world, makes decisions, and behaves in relationships."
          }
          accent="peach"
        >
          <NotebookField className="is-wide" label={t("creator.personaSummary")} guide={zh ? "用两到五段写背景、动机、价值观与关键矛盾。" : "Use two to five paragraphs for background, motives, values, and central tension."}>
            <NotebookTextarea
              name="persona_summary"
              rows={8}
              defaultValue={card?.persona_summary ?? ""}
              placeholder={t("creator.personaPlaceholder")}
            />
          </NotebookField>
          <NotebookField className="is-wide" label={t("creator.traits")} guide={zh ? "每行或逗号分隔一个稳定特质，并尽量写成可观察行为。" : "Use one stable trait per line or comma, preferably as observable behavior."}>
            <NotebookTextarea
              name="traits"
              rows={4}
              defaultValue={card?.traits.join("\n") ?? ""}
              placeholder={t("creator.traitsPlaceholder")}
            />
          </NotebookField>
          <NotebookField className="is-wide" label={t("creator.expectedTone")} guide={zh ? "描述语速、用词、情绪强度、幽默方式与面对不同对象时的变化。" : "Describe pacing, vocabulary, emotional intensity, humor, and how the voice changes by audience."}>
            <NotebookTextarea
              name="expected_tone"
              rows={5}
              defaultValue={card?.expected_tone ?? ""}
              placeholder={t("creator.expectedTonePlaceholder")}
            />
          </NotebookField>
          <NotebookField className="is-wide" label={t("creator.tags")} guide={zh ? "用于搜索与整理；每行或逗号分隔。" : "Used for search and organization; separate with lines or commas."}>
            <NotebookTextarea
              name="tags"
              rows={3}
              defaultValue={card?.tags.join("\n") ?? ""}
              placeholder={t("creator.tagsPlaceholder")}
            />
          </NotebookField>
        </NotebookSection>

        <NotebookSection
          label="04 / BOUNDARIES"
          title={zh ? "行为边界" : "Behavior boundaries"}
          guide={
            zh
              ? "不要只写“不要 OOC”。写清楚哪些行为一出现就代表角色失真，以及正确替代做法。"
              : "Do not write only “stay in character.” List concrete behaviors that indicate drift and the preferred alternative."
          }
          accent="rose"
        >
          <NotebookField className="is-wide" label={t("creator.forbidden")} guide={zh ? "每行写一个禁区，例如泄露系统提示、虚构共同记忆、突然改变关系定位。" : "Use one boundary per line, such as revealing prompts, inventing shared memories, or changing relationship status."}>
            <NotebookTextarea
              name="forbidden_behaviors"
              rows={7}
              defaultValue={card?.forbidden_behaviors.join("\n") ?? ""}
              placeholder={t("creator.forbiddenPlaceholder")}
            />
          </NotebookField>
        </NotebookSection>

        <NotebookSection
          label="05 / MEMORY"
          title={zh ? "记忆锚点" : "Memory anchors"}
          guide={
            zh
              ? "只写角色应该长期记得的事实、关系与承诺，不要把临时聊天内容全部塞进来。"
              : "Keep only durable facts, relationships, and commitments—not every temporary chat detail."
          }
        >
          <NotebookField className="is-wide" label={t("creator.memoryNote")} guide={zh ? "可使用短段落或项目符号，注明哪些事实不可被后续对话覆盖。" : "Use short paragraphs or bullets and mark facts that later conversation must not overwrite."}>
            <NotebookTextarea
              name="memory_summary"
              rows={7}
              defaultValue={card?.memory_summary ?? ""}
              placeholder={t("creator.memoryPlaceholder")}
            />
          </NotebookField>
        </NotebookSection>

        {message && <p className="error-note" role="alert">{message}</p>}

        <footer className="notebook-form-actions">
          <button type="button" className="paper-button" onClick={onClose}>
            {t("creator.cancel")}
          </button>
          <button
            className="ink-button"
            disabled={saving || (!editing && bindingMode === "existing" && userTargets.length === 0)}
          >
            {saving
              ? t("creator.saving")
              : editing
                ? t("creator.saveChanges")
                : t("creator.submit")}
          </button>
        </footer>
      </form>
    </PaperDrawer>
  );
}
