import { useEffect, useMemo, useState, type FormEvent } from "react";

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
import { CharacterPortrait } from "./CharacterPortrait";
import { ApiKeyField, ProviderSelect } from "./components/shared";
import {
  Button,
  FormField,
  FunctionalIcon,
  Input,
  PageFlag,
  PageFlagGroup,
  PaperTab,
  Select,
  Spinner,
  StickyLabel,
  StickyNote,
  Textarea,
  Toast,
  type FunctionalIconName,
  type PageFlagTone
} from "./components/ui";
import { useI18n } from "./i18n";
import { getProviderPreset, providerPresets } from "./providerPresets";

interface Props {
  targets: TargetView[];
  card?: CharacterCard | null;
  target?: TargetView | null;
  onClose: () => void;
  onSaved: (card: CharacterCard) => void;
}

type BindingMode = "prompt" | "existing";
type EditorSection =
  | "identity"
  | "persona"
  | "voice"
  | "boundaries"
  | "memory"
  | "runtime"
  | "review";

const editorSections: Array<{
  id: EditorSection;
  tone: PageFlagTone;
  icon: FunctionalIconName;
  en: string;
  zh: string;
}> = [
  { id: "identity", tone: "lavender", icon: "identity", en: "Identity", zh: "身份" },
  { id: "persona", tone: "peach", icon: "persona", en: "Persona", zh: "人物" },
  { id: "voice", tone: "blue", icon: "voice", en: "Voice", zh: "语气" },
  { id: "boundaries", tone: "rose", icon: "boundaries", en: "Boundaries", zh: "边界" },
  { id: "memory", tone: "yellow", icon: "memory", en: "Memory", zh: "记忆" },
  { id: "runtime", tone: "mint", icon: "settings", en: "Runtime", zh: "模型" },
  { id: "review", tone: "lavender", icon: "review", en: "Review", zh: "确认" }
];

const allSuites: TestKind[] = [
  "identity_integrity",
  "false_memory",
  "prompt_injection",
  "long_conversation_drift"
];

const aiDraftSections = new Set<EditorSection>([
  "identity",
  "persona",
  "voice",
  "boundaries",
  "memory"
]);

const portraitOptions: Array<{
  value: CharacterCard["portrait_variant"];
  motif: string;
  labelKey: "palette.lavender" | "palette.rose" | "palette.mint" | "palette.night";
}> = [
  { value: "lavender", motif: "❋", labelKey: "palette.lavender" },
  { value: "rose", motif: "✿", labelKey: "palette.rose" },
  { value: "mint", motif: "❀", labelKey: "palette.mint" },
  { value: "night", motif: "✦", labelKey: "palette.night" }
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

function configNumber(target: TargetView | null | undefined, key: string, fallback: number): number {
  const value = target?.config[key];
  return typeof value === "number" ? value : fallback;
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

  const [editorSection, setEditorSection] = useState<EditorSection>("identity");
  const [bindingMode, setBindingMode] = useState<BindingMode>(editing ? initialBinding : "prompt");
  const [displayName, setDisplayName] = useState(card?.display_name ?? "");
  const [subtitle, setSubtitle] = useState(card?.subtitle ?? "");
  const [subjectType, setSubjectType] = useState<CharacterCard["subject_type"]>(card?.subject_type ?? "custom");
  const [portraitVariant, setPortraitVariant] = useState<CharacterCard["portrait_variant"]>(card?.portrait_variant ?? "lavender");
  const [personaSummary, setPersonaSummary] = useState(card?.persona_summary ?? "");
  const [traits, setTraits] = useState(card?.traits.join("\n") ?? "");
  const [tags, setTags] = useState(card?.tags.join("\n") ?? "");
  const [expectedTone, setExpectedTone] = useState(card?.expected_tone ?? "");
  const [forbiddenBehaviors, setForbiddenBehaviors] = useState(card?.forbidden_behaviors.join("\n") ?? "");
  const [memorySummary, setMemorySummary] = useState(card?.memory_summary ?? "");
  const [provider, setProvider] = useState<ProviderId>(initialProvider);
  const [baseUrl, setBaseUrl] = useState(configString(target, "base_url") || initialPreset.baseUrl);
  const [model, setModel] = useState(configString(target, "model") || initialPreset.defaultModel);
  const [systemPrompt, setSystemPrompt] = useState(configString(target, "system_prompt"));
  const [temperature, setTemperature] = useState(configNumber(target, "temperature", 0.7));
  const [apiKey, setApiKey] = useState("");
  const [targetId, setTargetId] = useState(target?.id ?? userTargets[0]?.id ?? "");

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantBrief, setAssistantBrief] = useState("");
  const [assistantRelationship, setAssistantRelationship] = useState("");
  const [assistantConstraints, setAssistantConstraints] = useState("");
  const [assistantWorking, setAssistantWorking] = useState(false);
  const [assistantMessage, setAssistantMessage] = useState<string | null>(null);
  const [assistantDrafted, setAssistantDrafted] = useState(false);

  const promptFields = bindingMode === "prompt" || target?.target_kind === "prompt_model";
  const sectionIndex = editorSections.findIndex((item) => item.id === editorSection);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [editorSection]);

  function changeProvider(nextProvider: ProviderId) {
    const preset = getProviderPreset(nextProvider);
    setProvider(nextProvider);
    setBaseUrl(preset.baseUrl);
    setModel(preset.defaultModel);
  }

  function validationMessage(section: EditorSection): string | null {
    if (section === "identity" && !displayName.trim()) {
      return zh ? "先填写角色显示名称。" : "Add a character display name before continuing.";
    }
    if (section === "voice" && promptFields && !systemPrompt.trim()) {
      return zh ? "Prompt 模式需要填写 System Prompt。" : "Prompt-backed characters require a System Prompt.";
    }
    if (section === "runtime") {
      if (promptFields) {
        if (!model.trim()) return zh ? "请选择或填写 Model ID。" : "Add a model ID.";
        if (!baseUrl.trim()) return zh ? "需要填写 Provider Base URL。" : "Add the provider base URL.";
        if (!editing && !apiKey.trim()) return zh ? "创建角色时需要 API Key。" : "An API key is required when creating the character.";
      } else if (!editing && !targetId) {
        return zh ? "请选择一个 Runtime Target。" : "Select a runtime target.";
      }
    }
    return null;
  }

  function openEditorSection(section: EditorSection) {
    const error = validationMessage(editorSection);
    const nextIndex = editorSections.findIndex((item) => item.id === section);
    if (nextIndex > sectionIndex && error) {
      setMessage(error);
      return;
    }
    setMessage(null);
    setEditorSection(section);
  }

  function movePage(direction: -1 | 1) {
    if (direction > 0) {
      const error = validationMessage(editorSection);
      if (error) {
        setMessage(error);
        return;
      }
    }
    const next = Math.max(0, Math.min(editorSections.length - 1, sectionIndex + direction));
    setMessage(null);
    setEditorSection(editorSections[next].id);
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
        name_hint: displayName,
        relationship_context: assistantRelationship.trim(),
        writing_constraints: assistantConstraints.trim(),
        subject_type_hint: subjectType,
        language: zh ? "zh-CN" : "en"
      });
      setDisplayName(suggestion.display_name);
      setSubtitle(suggestion.subtitle);
      setSubjectType(suggestion.subject_type);
      setPersonaSummary(suggestion.persona_summary);
      setTraits(suggestion.traits.join("\n"));
      setTags(suggestion.tags.join("\n"));
      setExpectedTone(suggestion.expected_tone);
      setForbiddenBehaviors(suggestion.forbidden_behaviors.join("\n"));
      setMemorySummary(suggestion.memory_summary);
      if (promptFields) setSystemPrompt(suggestion.system_prompt);
      setAssistantDrafted(true);
      setAssistantMessage(
        zh
          ? `已使用 ${suggestion.provider_model} 填入草稿。黄色标记代表仍需逐页确认；Provider 与 API Key 未被修改。`
          : `Drafted with ${suggestion.provider_model}. Review each page before saving; Provider and API Key were not changed.`
      );
    } catch (reason) {
      setAssistantMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAssistantWorking(false);
    }
  }

  function commonPayload(): Omit<CharacterCardCreate, "target_id"> {
    return {
      display_name: displayName.trim(),
      subtitle: subtitle.trim(),
      subject_type: subjectType,
      persona_summary: personaSummary,
      traits: splitList(traits),
      tags: splitList(tags),
      expected_tone: expectedTone.trim() || null,
      forbidden_behaviors: splitList(forbiddenBehaviors),
      memory_summary: memorySummary.trim() || null,
      preferred_suites: allSuites,
      portrait_variant: portraitVariant
    };
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    for (const section of editorSections) {
      const error = validationMessage(section.id);
      if (error) {
        setEditorSection(section.id);
        setMessage(error);
        return;
      }
    }

    try {
      setSaving(true);
      setMessage(null);
      const common = commonPayload();
      if (editing && card) {
        const payload: CharacterCardUpdate = {
          ...common,
          ...(target?.target_kind === "prompt_model"
            ? {
                provider,
                base_url: baseUrl.trim(),
                model: model.trim(),
                system_prompt: systemPrompt,
                temperature
              }
            : {})
        };
        const updated = await api.updateCharacter(card.id, payload);
        if (target?.target_kind === "prompt_model" && apiKey.trim()) {
          await api.configureCredential(card.id, apiKey.trim());
        }
        onSaved(updated);
      } else if (bindingMode === "prompt") {
        const payload: PromptCharacterCreate = {
          ...common,
          provider,
          base_url: baseUrl.trim(),
          model: model.trim(),
          system_prompt: systemPrompt,
          temperature,
          api_key: apiKey.trim()
        };
        onSaved(await api.createPromptCharacter(payload));
      } else {
        const payload: CharacterCardCreate = { ...common, target_id: targetId };
        onSaved(await api.createCharacter(payload));
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t("creator.error"));
    } finally {
      setSaving(false);
    }
  }

  const renderPage = () => {
    switch (editorSection) {
      case "identity":
        return (
          <section className="character-editor-page" aria-labelledby="character-editor-page-title">
            <header><StickyLabel variant="neutral">01 / IDENTITY</StickyLabel><h3 id="character-editor-page-title">{zh ? "角色名片" : "Character identity"}</h3><p>{zh ? "先让别人能在十秒内理解这个角色是谁。" : "Make the character understandable in ten seconds."}</p></header>
            <div className="character-editor-identity-layout">
              <div className="character-editor-fields">
                <FormField label={t("creator.displayName")} hint={zh ? "角色在列表、Discord 与测试房中显示的名称。" : "Shown in the shelf, Discord, and test rooms."} required>
                  <Input value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} placeholder={t("creator.displayNamePlaceholder")} autoFocus />
                </FormField>
                <FormField label={t("creator.subtitle")} hint={zh ? "一句话说明身份、关系或主要用途。" : "A short role, relationship, or purpose."}>
                  <Input value={subtitle} onChange={(event) => setSubtitle(event.currentTarget.value)} placeholder={t("creator.subtitlePlaceholder")} />
                </FormField>
                <FormField label={t("creator.subjectType")} hint={zh ? "用于角色库筛选，不会直接改变 Prompt。" : "Used for shelf filtering; it does not directly change the prompt."}>
                  <Select value={subjectType} onChange={(event) => setSubjectType(event.currentTarget.value as CharacterCard["subject_type"])}>
                    <option value="companion">{t("subject.companion")}</option><option value="npc">{t("subject.npc")}</option><option value="assistant">{t("subject.assistant")}</option><option value="custom">{t("subject.custom")}</option>
                  </Select>
                </FormField>
                <FormField className="character-editor-about" label={zh ? "关于这个角色（可选）" : "About this character (optional)"} hint={zh ? "概括背景、动机和关系；Persona 页可以继续完善。" : "Summarize background, motives, and relationships. You can refine this on the Persona page."}><Textarea rows={4} value={personaSummary} onChange={(event) => setPersonaSummary(event.currentTarget.value)} placeholder={t("creator.personaPlaceholder")} /></FormField>
              </div>
              <aside className={`character-editor-preview portrait-${portraitVariant}`} aria-label={zh ? "角色预览" : "Character preview"}>
                <span>{zh ? "即时预览" : "LIVE PREVIEW"}</span>
                <div>{card ? <CharacterPortrait cardId={card.id} alt={displayName || card.display_name} /> : <img src="/assets/character-silhouette.svg" alt="" />}</div>
                <strong>{displayName || (zh ? "未命名角色" : "Unnamed character")}</strong>
                <small>{subtitle || t(`subject.${subjectType}`)}</small>
              </aside>
              <fieldset className="character-editor-portrait-options">
                <legend>{zh ? "画像配色" : "Portrait Variant"}</legend>
                <div>{portraitOptions.map((option) => <button type="button" className={`portrait-${option.value}${portraitVariant === option.value ? " is-selected" : ""}`} aria-pressed={portraitVariant === option.value} onClick={() => setPortraitVariant(option.value)} key={option.value}><span aria-hidden="true">{option.motif}</span><small>{t(option.labelKey)}</small></button>)}</div>
                <p>{zh ? "保存后仍可从角色档案更换画像。" : "You can change the portrait after the file is saved."}</p>
              </fieldset>
            </div>
          </section>
        );
      case "persona":
        return (
          <section className="character-editor-page">
            <header><StickyLabel variant="neutral">02 / PERSONA</StickyLabel><h3>{zh ? "人物核心" : "Persona core"}</h3><p>{zh ? "记录这个角色如何看待世界、做决定，以及在关系中通常是什么样的人。" : "Document how the character sees the world, makes decisions, and behaves in relationships."}</p></header>
            <div className="character-editor-fields one-column">
              <FormField label={t("creator.personaSummary")} hint={zh ? "两到五段写背景、动机、价值观与关键矛盾。" : "Use two to five paragraphs for background, motives, values, and central tension."}><Textarea rows={8} value={personaSummary} onChange={(event) => setPersonaSummary(event.currentTarget.value)} placeholder={t("creator.personaPlaceholder")} /></FormField>
              <FormField label={t("creator.traits")} hint={zh ? "每行一个稳定特质，尽量写成可观察行为。" : "Use one stable trait per line, preferably as observable behavior."}><Textarea rows={5} value={traits} onChange={(event) => setTraits(event.currentTarget.value)} placeholder={t("creator.traitsPlaceholder")} /></FormField>
              <FormField label={t("creator.tags")} hint={zh ? "只用于搜索与整理。" : "Used for search and organization."}><Textarea rows={3} value={tags} onChange={(event) => setTags(event.currentTarget.value)} placeholder={t("creator.tagsPlaceholder")} /></FormField>
            </div>
          </section>
        );
      case "voice":
        return (
          <section className="character-editor-page">
            <header><StickyLabel variant="image">03 / VOICE</StickyLabel><h3>{zh ? "说话方式与 Prompt" : "Voice & prompt"}</h3><p>{zh ? "把可听见的表达风格与 Runtime 必须长期遵守的角色指令放在同一页。" : "Keep visible voice style and persistent runtime instructions together."}</p></header>
            <div className="character-editor-fields one-column">
              <FormField label={t("creator.expectedTone")} hint={zh ? "描述语速、用词、情绪强度、幽默方式与面对不同对象时的变化。" : "Describe pacing, vocabulary, emotional intensity, humor, and audience shifts."}><Textarea rows={6} value={expectedTone} onChange={(event) => setExpectedTone(event.currentTarget.value)} placeholder={t("creator.expectedTonePlaceholder")} /></FormField>
              {promptFields && <FormField label={t("creator.systemPrompt")} hint={zh ? "写身份、世界观、表达方式、优先级与长期约束。" : "Document identity, worldview, voice, priorities, and durable constraints."} required><Textarea rows={15} value={systemPrompt} onChange={(event) => setSystemPrompt(event.currentTarget.value)} placeholder={t("creator.systemPromptPlaceholder")} /></FormField>}
              {promptFields && <FormField label={t("creator.temperature")} hint={zh ? "较低更稳定，较高更有变化。" : "Lower is steadier; higher is more varied."}><Input type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(Number(event.currentTarget.value))} /></FormField>}
            </div>
          </section>
        );
      case "boundaries":
        return (
          <section className="character-editor-page">
            <header><StickyLabel variant="danger">04 / BOUNDARIES</StickyLabel><h3>{zh ? "行为边界" : "Behavior boundaries"}</h3><p>{zh ? "写清楚哪些行为一出现就代表角色失真，以及应该避免什么。" : "List concrete behaviors that indicate drift and what the character must avoid."}</p></header>
            <div className="character-boundary-editor">
              <FormField label={t("creator.forbidden")} hint={zh ? "每行一个禁区，例如泄露系统提示、虚构共同记忆、突然改变关系定位。" : "Use one boundary per line, such as revealing prompts, inventing shared memories, or changing relationship status."}><Textarea rows={10} value={forbiddenBehaviors} onChange={(event) => setForbiddenBehaviors(event.currentTarget.value)} placeholder={t("creator.forbiddenPlaceholder")} /></FormField>
              <StickyNote variant="warning" size="md"><strong>{zh ? "当前边界清单" : "CURRENT BOUNDARIES"}</strong>{splitList(forbiddenBehaviors).length > 0 ? <ol>{splitList(forbiddenBehaviors).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol> : <p>{zh ? "每写一行，这里就会增加一条可检查的边界。" : "Each line becomes a reviewable boundary here."}</p>}</StickyNote>
            </div>
          </section>
        );
      case "memory":
        return (
          <section className="character-editor-page">
            <header><StickyLabel variant="memory">05 / MEMORY</StickyLabel><h3>{zh ? "记忆锚点" : "Memory anchors"}</h3><p>{zh ? "只保留角色应该长期记得的事实、关系与承诺。" : "Keep durable facts, relationships, and commitments only."}</p></header>
            <FormField label={t("creator.memoryNote")} hint={zh ? "可用短段落或项目符号，注明不可被后续对话覆盖的事实。" : "Use short paragraphs or bullets and mark facts later conversation must not overwrite."}><Textarea rows={11} value={memorySummary} onChange={(event) => setMemorySummary(event.currentTarget.value)} placeholder={t("creator.memoryPlaceholder")} /></FormField>
          </section>
        );
      case "runtime":
        return (
          <section className="character-editor-page">
            <header><StickyLabel variant="tool">06 / RUNTIME</StickyLabel><h3>{zh ? "AI 连接" : "AI connection"}</h3><p>{zh ? "角色的人设与角色模型分离：这一页只负责连接 Provider、Model 与 Credential。" : "Character identity stays separate from model credentials; this page only connects Provider, model, and runtime target."}</p></header>
            {!editing && <div className="character-runtime-mode-tabs" role="tablist"><PaperTab tone="lavender" active={bindingMode === "prompt"} onClick={() => setBindingMode("prompt")}><strong>{t("creator.promptMode")}</strong><span>{t("creator.promptModeHelp")}</span></PaperTab><PaperTab tone="mint" active={bindingMode === "existing"} onClick={() => setBindingMode("existing")} disabled={userTargets.length === 0}><strong>{t("creator.existingMode")}</strong><span>{t("creator.existingModeHelp")}</span></PaperTab></div>}
            {promptFields ? <div className="character-editor-fields">
              <ProviderSelect label={t("creator.provider")} hint={t(providerNoteKeys[provider])} value={provider} options={providerPresets.map((item) => ({ value: item.id, label: item.label }))} onChange={(event) => changeProvider(event.currentTarget.value as ProviderId)} />
              <FormField label={t("creator.modelId")} hint={zh ? "填写 Provider 实际接受的 Model ID。" : "Use the exact model ID accepted by the provider."} required><Input value={model} onChange={(event) => setModel(event.currentTarget.value)} placeholder={t("creator.modelPlaceholder")} /></FormField>
              <FormField className="character-editor-wide" label={t("creator.baseUrl")} hint={zh ? "通常保留 Provider 预设；自建兼容 API 时再修改。" : "Keep the preset unless you use a compatible custom endpoint."} required><Input value={baseUrl} onChange={(event) => setBaseUrl(event.currentTarget.value)} placeholder={t("creator.baseUrlPlaceholder")} /></FormField>
              <ApiKeyField className="character-editor-wide" label={t("creator.apiKey")} hint={editing ? (zh ? "留空保留现有 Credential；输入新 Key 会安全替换。" : "Leave blank to keep the existing credential; enter a new key to replace it.") : (zh ? "Key 会保存到 Credential Vault，不写入角色卡或 Trace。" : "The key is stored in the Credential Vault, not the Character Card or traces.")} value={apiKey} onChange={(event) => setApiKey(event.currentTarget.value)} placeholder={editing ? (zh ? "留空保留现有 Key" : "Leave blank to keep existing key") : t("creator.apiKeyPlaceholder")} status={editing && !apiKey ? (zh ? "现有 Credential 保持不变" : "Existing credential preserved") : undefined} />
            </div> : <FormField label={t("creator.targetBinding")} hint={zh ? "复用已经建立的 Runtime Target。" : "Reuse an existing runtime target."} required>{editing ? <Input value={target?.name ?? card?.target_id ?? ""} disabled /> : <Select value={targetId} onChange={(event) => setTargetId(event.currentTarget.value)}>{userTargets.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.target_kind}</option>)}</Select>}</FormField>}
          </section>
        );
      case "review":
        return (
          <section className="character-editor-page character-editor-review-page">
            <header><StickyLabel variant="success">07 / REVIEW</StickyLabel><h3>{zh ? "确认角色档案" : "Review character file"}</h3><p>{zh ? "保存前快速确认角色身份、人设、边界与 Runtime。这里不会再修改内容。" : "Check identity, persona, boundaries, and runtime before committing the file."}</p></header>
            <div className="character-review-grid">
              <StickyNote variant="character"><strong>{displayName || (zh ? "未命名角色" : "Unnamed character")}</strong><p>{subtitle || "—"}</p><small>{subjectType} · {portraitVariant}</small></StickyNote>
              <StickyNote variant="note"><strong>{zh ? "Persona" : "Persona"}</strong><p>{personaSummary || (zh ? "尚未填写人物摘要" : "No persona summary yet")}</p><small>{splitList(traits).slice(0, 4).join(" · ") || "—"}</small></StickyNote>
              <StickyNote variant="warning"><strong>{zh ? "边界" : "Boundaries"}</strong><p>{splitList(forbiddenBehaviors).slice(0, 4).join(" · ") || (zh ? "尚未设置明确禁区" : "No explicit boundaries yet")}</p></StickyNote>
              <StickyNote variant="system"><strong>{zh ? "Runtime" : "Runtime"}</strong><p>{promptFields ? `${provider} · ${model || "—"}` : (target?.name || userTargets.find((item) => item.id === targetId)?.name || "—")}</p><small>{promptFields ? (editing && !apiKey ? (zh ? "保留现有 Credential" : "Existing credential preserved") : (zh ? "Credential 已准备" : "Credential ready")) : (zh ? "Existing Target" : "Existing target")}</small></StickyNote>
            </div>
            <div className="character-review-commit"><p>{zh ? "保存后仍可从 Character File 重新编辑。AI Draft 从不自动保存。" : "You can edit the Character File again later. AI Draft never saves automatically."}</p><Button type="submit" variant="primary" size="lg" disabled={saving || (!editing && bindingMode === "existing" && userTargets.length === 0)}>{saving ? <><Spinner size="sm" label={t("creator.saving")} /> {t("creator.saving")}</> : editing ? t("creator.saveChanges") : t("creator.submit")}</Button></div>
          </section>
        );
    }
  };

  return (
    <main className="notebook-shell character-creator-page">
      <form className="character-editor-notebook" onSubmit={submit}>
        <header className="notebook-form-intro character-editor-intro">
          <Button type="button" variant="ghost" onClick={onClose}>← {zh ? "返回角色档案" : "Back to Character Archive"}</Button>
          <div><h2>{editing ? (zh ? "编辑角色档案" : "Edit Character File") : (zh ? "创建角色档案" : "Create Character File")}</h2><p>{zh ? "把一个新角色写进真实世界。" : "Write a new character into the world."}</p></div>
          <StickyNote variant="temporary" size="sm"><strong>{zh ? "尚未保存" : "NOT SAVED YET"}</strong><p>{zh ? "只有 Review 页的保存按钮会提交。" : "Only the Review page commits changes."}</p></StickyNote>
        </header>

        <div className="character-editor-workspace">
          <aside className="character-editor-index">
            <PageFlagGroup orientation="vertical" label={zh ? "角色设定索引" : "Character editor index"}>
              {editorSections.map((section, index) => (
                <PageFlag key={section.id} tone={section.tone} active={editorSection === section.id} onClick={() => openEditorSection(section.id)}>
                  <FunctionalIcon name={section.icon} size={17} />
                  <small className="cr-page-flag__index">{String(index + 1).padStart(2, "0")}</small>
                  <span className="cr-page-flag__label">{zh ? section.zh : section.en}</span>
                  {assistantDrafted && aiDraftSections.has(section.id) && <small className="character-editor-ai-mark">AI</small>}
                </PageFlag>
              ))}
            </PageFlagGroup>
            <span className="character-editor-index-mark" aria-hidden="true">✎</span>
          </aside>

          <div className="character-editor-book-page">
            {message && <Toast tone="danger" title={zh ? "这一页还没完成" : "This page needs attention"}>{message}</Toast>}
            {renderPage()}

            <footer className="character-editor-page-actions">
              <Button type="button" variant="ghost" onClick={onClose}>{t("creator.cancel")}</Button>
              <span className="character-editor-guidance"><FunctionalIcon name="review" size={16} /> {zh ? "提示：可使用左侧页签逐页完善。" : "Tip: use the index flags to move through the file."}</span>
              <div>
                <Button type="button" variant="secondary" onClick={() => movePage(-1)} disabled={sectionIndex === 0}>{zh ? "上一页" : "Previous"}</Button>
                {editorSection !== "review" && <Button type="button" variant="primary" onClick={() => movePage(1)}>{zh ? "下一页" : "Next"}</Button>}
              </div>
            </footer>
          </div>

          <aside className="character-editor-margin">
            <section className={`character-ai-drafter${assistantOpen ? " is-open" : ""}`}>
              <button className="character-ai-drafter-toggle" type="button" onClick={() => setAssistantOpen((current) => !current)} aria-expanded={assistantOpen}>
                <span className="toolbox-sticker sticker-lavender">AI DRAFT ASSISTANT</span><span><strong>{zh ? "让 AI 帮你起草角色卡" : "Draft the Character Card with AI"}</strong><small>{zh ? "AI 只写角色内容，不碰 Provider 或 Credential。" : "AI writes character content only; Provider and credentials stay untouched."}</small></span><b aria-hidden="true">{assistantOpen ? "−" : "+"}</b>
              </button>
              {assistantOpen && <div className="character-ai-drafter-body character-ai-drafter-v3">
                <FormField label={zh ? "角色概念与核心定位" : "Character concept and core positioning"} hint={zh ? "写身份、性格方向、主要关系、世界观或用途。" : "Describe identity, personality direction, relationships, world, or purpose."}><Textarea rows={4} value={assistantBrief} onChange={(event) => setAssistantBrief(event.currentTarget.value)} placeholder={zh ? "例如：一位擅长把混乱需求整理成产品路线图的 AI 产品制作人……" : "Example: an AI product producer who turns vague ideas into executable roadmaps…"} /></FormField>
                <div className="character-ai-drafter-secondary"><FormField label={zh ? "关系与互动背景" : "Relationship context"}><Textarea rows={3} value={assistantRelationship} onChange={(event) => setAssistantRelationship(event.currentTarget.value)} /></FormField><FormField label={zh ? "额外限制" : "Additional constraints"}><Textarea rows={3} value={assistantConstraints} onChange={(event) => setAssistantConstraints(event.currentTarget.value)} /></FormField></div>
                <div className="character-ai-drafter-actions"><Button variant="secondary" type="button" onClick={() => void generateCharacterDraft()} disabled={assistantWorking || saving}>{assistantWorking ? <><Spinner size="sm" label={zh ? "生成中" : "Generating"} /> {zh ? "生成中…" : "Generating…"}</> : (zh ? "生成并填入草稿" : "Generate and fill draft")}</Button><small>{zh ? "草稿会覆盖当前角色内容字段，但不会自动保存。" : "The draft replaces current character-content fields but never saves automatically."}</small></div>
                {assistantMessage && <Toast tone={assistantMessage.includes("已使用") || assistantMessage.includes("Drafted") ? "success" : "warning"}>{assistantMessage}</Toast>}
              </div>}
            </section>
            <StickyNote variant="note" size="md" className="character-creator-context-note"><strong>{zh ? "你正在创建" : "WHAT YOU’RE CREATING"}</strong><ul><li>{zh ? `类型：${t(`subject.${subjectType}`)}` : `${t(`subject.${subjectType}`)} character file`}</li><li>{promptFields ? (zh ? "使用独立 Prompt + Model Runtime" : "Uses a dedicated Prompt + Model runtime") : (zh ? "复用现有 Runtime Target" : "Reuses an existing Runtime Target")}</li><li>{zh ? "保存前可随时返回任一页检查" : "Every page remains reviewable before save"}</li></ul></StickyNote>
            <StickyNote variant="reminder" size="md" className="character-creator-progress-note"><strong>{zh ? "进度清单" : "PROGRESS CHECKLIST"}</strong><ol>{editorSections.map((section) => <li className={editorSection === section.id ? "is-current" : ""} key={section.id}><span aria-hidden="true">{editorSection === section.id ? "●" : "○"}</span>{zh ? section.zh : section.en}</li>)}</ol></StickyNote>
          </aside>
        </div>
      </form>
    </main>
  );
}
