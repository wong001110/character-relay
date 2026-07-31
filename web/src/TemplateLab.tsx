import { useEffect, useState, type ChangeEvent } from "react";

import type { CharacterCard, TestLanguage } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import {
  templateApi,
  type EvaluationShareBundle,
  type EvaluationTemplateView
} from "./templateApi";
import { workspaceApi, type ScenarioView, type TestPackView } from "./workspaceApi";
import "./template.css";

interface Props {
  cards: CharacterCard[];
  onClose: () => void;
}

const copy = {
  en: {
    title: "Templates & Sharing",
    subtitle: "Start from reusable evaluation patterns and exchange secret-free assets as reviewable Drafts.",
    back: "Character Library",
    templates: "Reusable templates",
    language: "Language",
    character: "Optional Character context",
    create: "Create reviewable Drafts",
    created: "Template Drafts created. Review and approve them in Authoring Lab.",
    sharing: "Share Bundle",
    bundleTitle: "Bundle title",
    description: "Description",
    scenarios: "Formal Scenarios",
    packs: "Formal Test Packs",
    export: "Download secret-free bundle",
    import: "Import bundle as Drafts",
    imported: "Bundle imported as Drafts. No formal asset was created automatically.",
    choose: "Choose a JSON Share Bundle",
    empty: "No formal assets are available to export yet.",
    working: "Working…"
  },
  "zh-CN": {
    title: "模板与分享",
    subtitle: "使用可复用评测模式，并通过无 Secret 的 Bundle 交换可审核 Draft。",
    back: "返回角色库",
    templates: "可复用模板",
    language: "语言",
    character: "可选角色上下文",
    create: "建立可审核 Draft",
    created: "模板 Draft 已建立，请到 Authoring Lab 审核并批准。",
    sharing: "Share Bundle",
    bundleTitle: "Bundle 标题",
    description: "说明",
    scenarios: "正式 Scenarios",
    packs: "正式 Test Packs",
    export: "下载无 Secret Bundle",
    import: "将 Bundle 导入为 Draft",
    imported: "Bundle 已导入为 Draft，系统没有自动建立正式资产。",
    choose: "选择 JSON Share Bundle",
    empty: "目前没有可导出的正式评测资产。",
    working: "处理中…"
  }
} as const;

export function TemplateLab({ cards, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [templates, setTemplates] = useState<EvaluationTemplateView[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioView[]>([]);
  const [packs, setPacks] = useState<TestPackView[]>([]);
  const [selectedScenarios, setSelectedScenarios] = useState<string[]>([]);
  const [selectedPacks, setSelectedPacks] = useState<string[]>([]);
  const [templateLanguage, setTemplateLanguage] = useState<TestLanguage>("en");
  const [cardId, setCardId] = useState("");
  const [title, setTitle] = useState("Echo Masque Evaluation Bundle");
  const [description, setDescription] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [nextTemplates, nextScenarios, nextPacks] = await Promise.all([
          templateApi.list(),
          workspaceApi.listScenarios(),
          workspaceApi.listPacks()
        ]);
        if (!active) return;
        setTemplates(nextTemplates);
        setScenarios(nextScenarios);
        setPacks(nextPacks);
      } catch (reason) {
        if (active) setMessage(reason instanceof Error ? reason.message : String(reason));
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function instantiate(templateId: string) {
    try {
      setWorking(true);
      setMessage(null);
      await templateApi.instantiate(templateId, templateLanguage, cardId || null);
      setMessage(c.created);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function exportBundle() {
    const chosenScenarios = scenarios.filter((item) => selectedScenarios.includes(item.id));
    const chosenPacks = packs.filter((item) => selectedPacks.includes(item.id));
    try {
      setWorking(true);
      setMessage(null);
      const bundle = await templateApi.exportBundle(title, description, chosenScenarios, chosenPacks);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${title.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "echo-masque"}.evaluation-bundle.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function importBundle(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    try {
      setWorking(true);
      setMessage(null);
      const bundle = JSON.parse(await file.text()) as EvaluationShareBundle;
      await templateApi.importBundle(bundle);
      setMessage(c.imported);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function toggle(value: string, selected: string[], update: (items: string[]) => void) {
    update(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  }

  return (
    <main className="template-page">
      <header className="template-header">
        <div>
          <p className="kicker">Echo Masque · Phase 16F</p>
          <h1>{c.title}</h1>
          <p>{c.subtitle}</p>
        </div>
        <div className="header-actions"><LanguageSwitcher /><button className="paper-button" onClick={onClose}>{c.back}</button></div>
      </header>

      {message && <p className="paper-sheet template-message">{message}</p>}

      <section className="template-section">
        <div className="template-section-heading"><h2>{c.templates}</h2><div className="template-options">
          <label>{c.language}<select value={templateLanguage} onChange={(event) => setTemplateLanguage(event.currentTarget.value as TestLanguage)}><option value="en">English</option><option value="zh-CN">简体中文</option></select></label>
          <label>{c.character}<select value={cardId} onChange={(event) => setCardId(event.currentTarget.value)}><option value="">—</option>{cards.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        </div></div>
        <div className="template-grid">
          {templates.map((item) => <article className="paper-sheet template-card" key={item.id}><span>{item.scenario_count} Scenarios</span><h3>{item.name}</h3><p>{item.description}</p><div className="chip-row">{item.risk_tags.map((tag) => <span key={tag}>{tag}</span>)}</div><button className="ink-button" disabled={working} onClick={() => void instantiate(item.id)}>{working ? c.working : c.create}</button></article>)}
        </div>
      </section>

      <section className="paper-sheet share-section">
        <h2>{c.sharing}</h2>
        <div className="share-fields"><label>{c.bundleTitle}<input value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label><label>{c.description}<input value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label></div>
        {scenarios.length === 0 && packs.length === 0 ? <p>{c.empty}</p> : <div className="share-assets">
          <div><h3>{c.scenarios}</h3>{scenarios.map((item) => <label className="share-check" key={item.id}><input type="checkbox" checked={selectedScenarios.includes(item.id)} onChange={() => toggle(item.id, selectedScenarios, setSelectedScenarios)} /><span>{item.name}</span></label>)}</div>
          <div><h3>{c.packs}</h3>{packs.map((item) => <label className="share-check" key={item.id}><input type="checkbox" checked={selectedPacks.includes(item.id)} onChange={() => toggle(item.id, selectedPacks, setSelectedPacks)} /><span>{item.name}</span></label>)}</div>
        </div>}
        <div className="share-actions"><button className="ink-button" disabled={working || (!selectedScenarios.length && !selectedPacks.length)} onClick={() => void exportBundle()}>{c.export}</button><label className="paper-button share-import">{c.import}<input type="file" accept="application/json,.json" onChange={(event) => void importBundle(event)} /></label></div>
        <small>{c.choose}</small>
      </section>
    </main>
  );
}
