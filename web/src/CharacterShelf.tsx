import { useEffect, useMemo, useState } from "react";

import { api, type CharacterCard, type CredentialStatus, type TargetView } from "./api";
import { CharacterPortrait } from "./CharacterPortrait";
import { characterPortraitApi } from "./characterPortraitApi";
import {
  Button,
  EmptyState,
  FunctionalIcon,
  PageFlag,
  PageFlagGroup,
  SearchField,
  StickyLabel,
  StickyNote,
  Toast,
  type FunctionalIconName,
  type PageFlagTone
} from "./components/ui";
import type { CharacterDeployment } from "./deploymentApi";
import { useI18n } from "./i18n";
import { SemanticProfilePanel } from "./SemanticProfilePanel";

interface Props {
  cards: CharacterCard[];
  targets: TargetView[];
  deployments: CharacterDeployment[];
  selectedCard: CharacterCard | null;
  selectedFileSection?: FileSection;
  error: string | null;
  demoMode?: boolean;
  onCreate: () => void;
  onOpenFile: (card: CharacterCard) => void;
  onCloseFile: () => void;
  onFileSectionChange?: (section: FileSection) => void;
  onEdit: (card: CharacterCard) => void;
  onPrompt: (card: CharacterCard) => void;
  onEnter: (card: CharacterCard) => void;
  onDeploy: (card: CharacterCard) => void;
}

type ArchiveFilter = "all" | "deployed" | "not-deployed" | "needs-setup";
export type FileSection = "profile" | "persona" | "prompt" | "memory" | "runtime" | "deployments";

const PAGE_SIZE = 9;

const subjectKeys = {
  companion: "subject.companion",
  npc: "subject.npc",
  assistant: "subject.assistant",
  custom: "subject.custom"
} as const;

const fileSections: Array<{
  id: FileSection;
  tone: PageFlagTone;
  icon: FunctionalIconName;
  en: string;
  zh: string;
}> = [
  { id: "profile", tone: "lavender", icon: "identity", en: "Profile", zh: "档案" },
  { id: "persona", tone: "peach", icon: "persona", en: "Persona", zh: "人设" },
  { id: "prompt", tone: "blue", icon: "behavior", en: "Prompt", zh: "提示词" },
  { id: "memory", tone: "yellow", icon: "memory", en: "Memory", zh: "记忆" },
  { id: "runtime", tone: "mint", icon: "settings", en: "Runtime", zh: "运行时" },
  { id: "deployments", tone: "rose", icon: "deployment", en: "Deployments", zh: "部署" }
];

const archiveFilters: Array<{
  id: ArchiveFilter;
  tone: PageFlagTone;
  icon: FunctionalIconName;
  en: string;
  zh: string;
  enSubtitle: string;
  zhSubtitle: string;
}> = [
  { id: "all", tone: "lavender", icon: "archive", en: "All", zh: "全部", enSubtitle: "Every file", zhSubtitle: "全部档案" },
  { id: "deployed", tone: "mint", icon: "status-check", en: "Deployed", zh: "已部署", enSubtitle: "Has a deployment", zhSubtitle: "已有部署" },
  { id: "not-deployed", tone: "blue", icon: "cloud", en: "Not Deployed", zh: "未部署", enSubtitle: "Archive only", zhSubtitle: "仅在档案册" },
  { id: "needs-setup", tone: "peach", icon: "warning", en: "Needs Setup", zh: "需要设置", enSubtitle: "Target unavailable", zhSubtitle: "Target 不可用" }
];

function formatCharacterDate(value: string, zh: boolean): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "—";
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    year: "numeric",
    month: "short",
    day: "2-digit"
  }).format(date);
}

function configText(target: TargetView | null, key: string): string {
  const value = target?.config[key];
  return typeof value === "string" ? value : "";
}

function configNumber(target: TargetView | null, key: string): number | null {
  const value = target?.config[key];
  return typeof value === "number" ? value : null;
}

function deploymentNeedsAttention(item: CharacterDeployment): boolean {
  return ["error", "offline", "disconnected"].includes(item.status);
}

export function CharacterShelf({
  cards,
  targets,
  deployments,
  selectedCard,
  selectedFileSection,
  error,
  demoMode = false,
  onCreate,
  onOpenFile,
  onCloseFile,
  onFileSectionChange,
  onEdit,
  onPrompt,
  onEnter,
  onDeploy
}: Props) {
  const { language, t } = useI18n();
  const zh = language === "zh-CN";
  const [query, setQuery] = useState("");
  const [archiveFilter, setArchiveFilter] = useState<ArchiveFilter>("all");
  const [page, setPage] = useState(1);
  const [localFileSection, setLocalFileSection] = useState<FileSection>("profile");
  const fileSection = selectedFileSection ?? localFileSection;
  const [semanticCard, setSemanticCard] = useState<CharacterCard | null>(null);
  const [portraitVersions, setPortraitVersions] = useState<Record<string, number>>({});
  const [portraitWorking, setPortraitWorking] = useState<string | null>(null);
  const [portraitMessage, setPortraitMessage] = useState<string | null>(null);
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null);
  const [credentialError, setCredentialError] = useState<string | null>(null);

  const targetById = useMemo(
    () => new Map(targets.map((target) => [target.id, target])),
    [targets]
  );
  const deploymentsByCard = useMemo(() => {
    const grouped = new Map<string, CharacterDeployment[]>();
    for (const deployment of deployments) {
      const current = grouped.get(deployment.character_card_id) ?? [];
      current.push(deployment);
      grouped.set(deployment.character_card_id, current);
    }
    return grouped;
  }, [deployments]);

  const archiveCounts = useMemo(() => {
    let deployed = 0;
    let needsSetup = 0;
    for (const card of cards) {
      if ((deploymentsByCard.get(card.id)?.length ?? 0) > 0) deployed += 1;
      if (!targetById.has(card.target_id)) needsSetup += 1;
    }
    return {
      all: cards.length,
      deployed,
      notDeployed: cards.length - deployed,
      needsSetup
    };
  }, [cards, deploymentsByCard, targetById]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return cards.filter((card) => {
      const searchable = [
        card.display_name,
        card.subtitle,
        card.persona_summary,
        ...card.traits,
        ...card.tags
      ]
        .join(" ")
        .toLocaleLowerCase();
      const deployed = (deploymentsByCard.get(card.id)?.length ?? 0) > 0;
      const needsSetup = !targetById.has(card.target_id);
      const matchesFilter =
        archiveFilter === "all" ||
        (archiveFilter === "deployed" && deployed) ||
        (archiveFilter === "not-deployed" && !deployed) ||
        (archiveFilter === "needs-setup" && needsSetup);
      return (!needle || searchable.includes(needle)) && matchesFilter;
    });
  }, [archiveFilter, cards, deploymentsByCard, query, targetById]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageCards = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selectedTarget = selectedCard ? targetById.get(selectedCard.target_id) ?? null : null;
  const selectedDeployments = selectedCard
    ? deploymentsByCard.get(selectedCard.id) ?? []
    : [];

  useEffect(() => {
    setPage(1);
  }, [archiveFilter, query]);

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  useEffect(() => {
    if (selectedFileSection === undefined) setLocalFileSection("profile");
    setCredentialStatus(null);
    setCredentialError(null);
    if (!selectedCard) return;
    let current = true;
    void api
      .getCredentialStatus(selectedCard.id)
      .then((status) => {
        if (current) setCredentialStatus(status);
      })
      .catch((reason: unknown) => {
        if (current) setCredentialError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      current = false;
    };
  }, [selectedCard?.id, selectedFileSection]);

  function selectFileSection(next: FileSection) {
    if (onFileSectionChange) onFileSectionChange(next);
    else setLocalFileSection(next);
  }

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [fileSection, selectedCard?.id]);

  async function uploadPortrait(card: CharacterCard, file: File | null) {
    if (!file) return;
    try {
      setPortraitWorking(card.id);
      setPortraitMessage(null);
      await characterPortraitApi.upload(card.id, file);
      setPortraitVersions((current) => ({ ...current, [card.id]: Date.now() }));
      setPortraitMessage(
        zh
          ? `已更新 ${card.display_name} 的角色图片。未设置 Deployment icon 时，Discord 会继承这张图片。`
          : `Updated ${card.display_name}'s portrait. Discord inherits it when the Deployment has no custom icon.`
      );
    } catch (reason) {
      setPortraitMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPortraitWorking(null);
    }
  }

  async function removePortrait(card: CharacterCard) {
    try {
      setPortraitWorking(card.id);
      setPortraitMessage(null);
      await characterPortraitApi.remove(card.id);
      setPortraitVersions((current) => ({ ...current, [card.id]: Date.now() }));
      setPortraitMessage(
        zh ? `已移除 ${card.display_name} 的角色图片。` : `Removed ${card.display_name}'s portrait.`
      );
    } catch (reason) {
      setPortraitMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPortraitWorking(null);
    }
  }

  function renderFilePage(card: CharacterCard) {
    const activeDeployments = selectedDeployments.filter((item) => item.status === "active");
    const attentionDeployments = selectedDeployments.filter(deploymentNeedsAttention);
    const primaryDeployment = activeDeployments[0] ?? selectedDeployments[0] ?? null;
    const prompt = configText(selectedTarget, "system_prompt");
    const temperature = configNumber(selectedTarget, "temperature");

    if (fileSection === "persona") {
      return (
        <section className="character-file-section character-file-persona">
          <header><StickyLabel variant="neutral">PERSONA RECORD</StickyLabel><h2>{zh ? "人物核心与表达" : "Persona & voice"}</h2></header>
          <div className="character-file-reading-grid">
            <article><span>{zh ? "人物摘要" : "Persona summary"}</span><p>{card.persona_summary || "—"}</p></article>
            <article><span>{zh ? "说话方式" : "Expected tone"}</span><p>{card.expected_tone || "—"}</p></article>
            <article><span>{zh ? "稳定特质" : "Stable traits"}</span><div className="character-file-tag-cloud">{card.traits.length > 0 ? card.traits.map((trait) => <StickyLabel variant="neutral" key={trait}>{trait}</StickyLabel>) : <p>—</p>}</div></article>
            <article><span>{zh ? "行为边界" : "Forbidden behaviors"}</span>{card.forbidden_behaviors.length > 0 ? <ol>{card.forbidden_behaviors.map((item) => <li key={item}>{item}</li>)}</ol> : <p>—</p>}</article>
          </div>
        </section>
      );
    }

    if (fileSection === "prompt") {
      return (
        <section className="character-file-section character-file-prompt">
          <header><StickyLabel variant="image">PROMPT MANUSCRIPT</StickyLabel><h2>{zh ? "角色提示词" : "Character prompt"}</h2><p>{zh ? "这里展示当前 Runtime Target 中真实保存的原始 Prompt；编译层仍由 Prompt Inspector 检查。" : "This is the raw prompt stored on the current Runtime Target. Use Prompt Inspector for the compiled layers."}</p></header>
          {selectedTarget?.target_kind === "prompt_model" && prompt ? <pre><code>{prompt}</code></pre> : <EmptyState title={zh ? "这个 Target 没有可读取的原始 Prompt" : "No readable raw prompt for this target"} description={zh ? "现有 Target 类型不会在角色档案中公开 Prompt 内容。" : "The current target type does not expose prompt content in the character file."} />}
          <div className="character-file-section-actions"><Button variant="secondary" onClick={() => onPrompt(card)}>{zh ? "打开 Prompt Inspector" : "Open Prompt Inspector"}</Button></div>
        </section>
      );
    }

    if (fileSection === "memory") {
      return (
        <section className="character-file-section character-file-memory">
          <header><StickyLabel variant="memory">MEMORY NOTE</StickyLabel><h2>{zh ? "权威记忆锚点" : "Authoritative memory anchors"}</h2><p>{zh ? "只显示角色卡当前保存的 Memory Summary，不推断未来的记忆系统状态。" : "Only the Character Card's saved Memory Summary is shown here."}</p></header>
          <StickyNote variant="reminder" size="lg"><strong>{zh ? "角色长期记得" : "Durable character memory"}</strong><p>{card.memory_summary || (zh ? "尚未写入记忆摘要。" : "No memory summary has been filed.")}</p></StickyNote>
        </section>
      );
    }

    if (fileSection === "runtime") {
      return (
        <section className="character-file-section character-file-runtime">
          <header><StickyLabel variant="tool">RUNTIME SHEET</StickyLabel><h2>{zh ? "模型与连接" : "Model & connection"}</h2><p>{zh ? "技术字段来自当前 Target；Credential 只显示状态，绝不显示密钥。" : "Technical fields come from the current Target. Credentials are represented by status only."}</p></header>
          {selectedTarget ? <dl className="character-runtime-facts">
            <div><dt>Target</dt><dd>{selectedTarget.name}</dd></div>
            <div><dt>{zh ? "类型" : "Kind"}</dt><dd>{selectedTarget.target_kind}</dd></div>
            {configText(selectedTarget, "provider") && <div><dt>Provider</dt><dd>{configText(selectedTarget, "provider")}</dd></div>}
            {configText(selectedTarget, "model") && <div><dt>Model</dt><dd>{configText(selectedTarget, "model")}</dd></div>}
            {configText(selectedTarget, "base_url") && <div className="wide"><dt>Base URL</dt><dd>{configText(selectedTarget, "base_url")}</dd></div>}
            {temperature !== null && <div><dt>Temperature</dt><dd>{temperature}</dd></div>}
            <div><dt>Credential</dt><dd>{credentialStatus ? (credentialStatus.configured ? (zh ? "已配置" : "Configured") : (zh ? "缺失" : "Missing")) : credentialError ? (zh ? "状态不可用" : "Status unavailable") : (zh ? "检查中…" : "Checking…")}</dd></div>
          </dl> : <EmptyState title={zh ? "Runtime Target 不可用" : "Runtime Target unavailable"} description={zh ? "此角色当前绑定的 Target 不在可访问列表中。" : "The Character's bound Target is not in the accessible target list."} />}
          {!demoMode && <div className="character-file-section-actions"><Button variant="secondary" onClick={() => onEdit(card)}>{zh ? "编辑 Runtime 设置" : "Edit runtime settings"}</Button></div>}
        </section>
      );
    }

    if (fileSection === "deployments") {
      return (
        <section className="character-file-section character-file-deployments">
          <header><StickyLabel variant="link">DEPLOYMENT FILES</StickyLabel><h2>{zh ? "角色所在位置" : "Where this character lives"}</h2><p>{zh ? "每一张记录都来自真实 Deployment。" : "Every record below comes from a real Deployment."}</p></header>
          {selectedDeployments.length > 0 ? <div className="character-file-deployment-list">{selectedDeployments.map((deployment) => <article key={deployment.id}>
            <div><StickyLabel variant={deployment.status === "active" ? "success" : deploymentNeedsAttention(deployment) ? "danger" : "warning"}>{deployment.status}</StickyLabel><h3>{deployment.server_profile_name || deployment.workspace_name || deployment.platform}</h3></div>
            <dl><div><dt>{zh ? "参与方式" : "Participation"}</dt><dd>{deployment.participation_mode}</dd></div><div><dt>{zh ? "记忆范围" : "Memory"}</dt><dd>{deployment.memory_scope}</dd></div>{deployment.channel_name && <div><dt>{zh ? "频道" : "Channel"}</dt><dd>{deployment.channel_name}</dd></div>}</dl>
          </article>)}</div> : <EmptyState title={zh ? "尚未部署" : "Not deployed yet"} description={zh ? "这个角色目前只保存在档案册中。" : "This character currently lives only in the archive."} action={<Button variant="primary" onClick={() => onDeploy(card)}>{zh ? "创建部署" : "Create deployment"}</Button>} />}
          {selectedDeployments.length > 0 && <div className="character-file-section-actions"><Button variant="secondary" onClick={() => onDeploy(card)}>{zh ? "打开 Deployment Workspace" : "Open Deployment Workspace"}</Button></div>}
        </section>
      );
    }

    return (
      <section className="character-file-section character-file-profile">
        <div className="character-file-profile-hero">
          <div className={`character-file-polaroid portrait-${card.portrait_variant}`}>
            <CharacterPortrait cardId={card.id} version={portraitVersions[card.id] ?? 0} alt={card.display_name} />
            <strong>{card.display_name}</strong>
            <span>{card.portrait_variant.toLocaleUpperCase()} · PORTRAIT</span>
          </div>
          <div className="character-file-identity">
            <span>{zh ? "角色档案" : "CHARACTER FILE"}</span>
            <h1>{card.display_name}</h1>
            <p className="character-file-subtitle">{card.subtitle || t(subjectKeys[card.subject_type])}</p>
            <p>{card.persona_summary || (zh ? "尚未填写人物摘要。" : "No persona summary has been filed.")}</p>
            <div className="character-file-tag-cloud"><StickyLabel variant="neutral">{t(subjectKeys[card.subject_type])}</StickyLabel>{card.traits.slice(0, 5).map((trait) => <StickyLabel variant="neutral" key={trait}>{trait}</StickyLabel>)}</div>
          </div>
          <div className="character-file-status-stack">
            <div className={`character-file-deployment-stamp${activeDeployments.length > 0 ? " is-active" : ""}`}>{activeDeployments.length > 0 ? (zh ? "已部署" : "DEPLOYED") : (zh ? "已归档" : "FILED")}</div>
            <StickyNote variant={attentionDeployments.length > 0 ? "warning" : "system"} size="md" className="character-file-status-note">
              <strong>{zh ? "当前状态" : "Current status"}</strong>
              <p>{selectedDeployments.length === 0 ? (zh ? "尚未部署" : "Not deployed") : zh ? `${activeDeployments.length} 个活跃部署` : `${activeDeployments.length} active deployment(s)`}</p>
              {primaryDeployment && <dl><div><dt>{zh ? "位置" : "Location"}</dt><dd>{primaryDeployment.server_profile_name || primaryDeployment.workspace_name || primaryDeployment.platform}</dd></div>{primaryDeployment.channel_name && <div><dt>{zh ? "频道" : "Channel"}</dt><dd>#{primaryDeployment.channel_name}</dd></div>}<div><dt>{zh ? "参与方式" : "Participation"}</dt><dd>{primaryDeployment.participation_mode}</dd></div><div><dt>{zh ? "记忆" : "Memory"}</dt><dd>{primaryDeployment.memory_scope}</dd></div></dl>}
              <small>{attentionDeployments.length > 0 ? (zh ? `${attentionDeployments.length} 个部署需要注意` : `${attentionDeployments.length} deployment(s) need attention`) : selectedTarget ? selectedTarget.name : (zh ? "Target 不可用" : "Target unavailable")}</small>
            </StickyNote>
          </div>
        </div>

        <div className="character-file-profile-records">
          <article className="character-file-about-sheet"><h2><FunctionalIcon name="identity" size={18} /> {zh ? `关于 ${card.display_name}` : `About ${card.display_name}`}</h2><p>{card.persona_summary || "—"}</p><dl><div><dt>{zh ? "创建于" : "Created"}</dt><dd>{formatCharacterDate(card.created_at, zh)}</dd></div><div><dt>{zh ? "所有者 ID" : "Owner ID"}</dt><dd>{card.owner_id}</dd></div><div><dt>Character ID</dt><dd>{card.id}</dd></div></dl></article>
          <article className="character-file-tests-sheet"><h2><FunctionalIcon name="review" size={18} /> {zh ? "偏好测试" : "Preferred Tests"}</h2>{card.preferred_suites.length > 0 ? <ul>{card.preferred_suites.map((suite) => <li key={suite}><span>{suite.replaceAll("_", " ")}</span><FunctionalIcon name="status-check" size={16} /></li>)}</ul> : <p>{zh ? "尚未选择偏好测试。" : "No preferred tests selected."}</p>}</article>
          <StickyNote variant="temporary" size="md" className="character-file-studio-note"><strong>{zh ? "工作室笔记" : "STUDIO NOTE"}</strong><p>{card.expected_tone || card.persona_summary || (zh ? "这个角色尚未留下额外的表达笔记。" : "No additional voice note has been filed for this character.")}</p><small>{card.tags.length > 0 ? card.tags.slice(0, 4).map((tag) => `#${tag}`).join(" · ") : t(subjectKeys[card.subject_type])}</small></StickyNote>
        </div>

        {!demoMode && <section className="character-file-portrait-tools">
          <strong>{zh ? "角色图片" : "Portrait"}</strong>
          <div>
            <label className="cr-button cr-button--secondary cr-control--sm character-file-upload-button">
              {portraitWorking === card.id ? (zh ? "处理中…" : "Working…") : (zh ? "更换图片" : "Change image")}
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" disabled={portraitWorking === card.id} onChange={(event) => { const file = event.currentTarget.files?.[0] ?? null; void uploadPortrait(card, file); event.currentTarget.value = ""; }} />
            </label>
            <Button variant="ghost" size="sm" disabled={portraitWorking === card.id} onClick={() => void removePortrait(card)}>{zh ? "移除图片" : "Remove image"}</Button>
            <Button variant="ghost" size="sm" onClick={() => setSemanticCard(card)}>Semantic Profile</Button>
          </div>
        </section>}
      </section>
    );
  }

  if (selectedCard) {
    return (
      <main className="notebook-shell character-file-page">
        <header className="character-file-page-header">
          <Button variant="ghost" onClick={onCloseFile}>← {zh ? "返回角色档案册" : "Back to Character Archive"}</Button>
          <div className="character-file-title"><span>{selectedCard.display_name.toLocaleUpperCase()} / CHARACTER FILE</span><small>{zh ? "正式角色记录" : "Formal character record"}</small></div>
          <div className="character-file-top-actions"><Button variant="secondary" onClick={() => onEnter(selectedCard)}>{zh ? "测试角色" : "Test Character"}</Button>{!demoMode && <Button variant="primary" onClick={() => onEdit(selectedCard)}>{zh ? "编辑角色" : "Edit Character"}</Button>}<Button variant="secondary" onClick={() => onDeploy(selectedCard)}>{zh ? "部署" : "Deploy"}</Button></div>
        </header>
        {portraitMessage && <Toast tone="success" title={zh ? "角色图片已更新" : "Portrait updated"}>{portraitMessage}</Toast>}
        <div className="character-file-page-layout">
          <aside className="character-file-index">
            <PageFlagGroup orientation="vertical" label={zh ? "角色档案索引" : "Character file index"}>{fileSections.map((section) => <PageFlag key={section.id} tone={section.tone} active={fileSection === section.id} onClick={() => selectFileSection(section.id)}><FunctionalIcon name={section.icon} size={18} /><span className="cr-page-flag__label">{zh ? section.zh : section.en}</span></PageFlag>)}</PageFlagGroup>
            <span className="character-file-index-mark" aria-hidden="true">♡</span>
          </aside>
          <article className="character-file-paper">{renderFilePage(selectedCard)}</article>
        </div>
        <footer className="character-file-system-note" aria-label={zh ? "角色档案系统状态" : "Character file system status"}>
          <strong><FunctionalIcon name="archive" size={17} /> {zh ? "系统笔记" : "SYSTEM NOTE"}</strong>
          <span><i className="is-ready" />{zh ? "档案已读取" : "File loaded"}</span>
          <span><i className={selectedTarget ? "is-ready" : ""} />Runtime {selectedTarget ? (zh ? "可用" : "ready") : (zh ? "不可用" : "unavailable")}</span>
          <span><i className={credentialStatus?.configured ? "is-ready" : ""} />Credential {credentialStatus ? (credentialStatus.configured ? (zh ? "已配置" : "configured") : (zh ? "缺失" : "missing")) : (zh ? "检查中" : "checking")}</span>
        </footer>
        {semanticCard && <SemanticProfilePanel card={semanticCard} zh={zh} demoMode={demoMode} onClose={() => setSemanticCard(null)} />}
      </main>
    );
  }

  return (
    <main className="notebook-shell character-archive-page">
      <header className="character-archive-header">
        <div className="character-archive-title-sheet"><span>CHARACTER ARCHIVE</span><h1>{zh ? "角色档案册" : "Character Archive"}</h1><b aria-hidden="true">✦</b></div>
        <div className="character-archive-intro"><p>{demoMode ? (zh ? "浏览共享角色档案与真实运行配置。" : "Browse shared Character files and their real runtime configuration.") : (zh ? "在这里创建、整理并继续完善你的 AI 角色档案。" : "Create, organize, and keep refining the AI characters in your workspace.")}</p><img src="/assets/brand/character-relay-mark.png" alt="" /></div>
        <StickyNote variant="temporary" size="sm" pinned className="character-archive-overview-note"><strong>ARCHIVE NOTE</strong><ul><li>{archiveCounts.deployed} {zh ? "个角色已有部署" : "character file(s) have deployments"}</li><li>{archiveCounts.needsSetup} {zh ? "个角色的 Target 不可用" : "character file(s) have unavailable targets"}</li><li>{archiveCounts.notDeployed} {zh ? "个角色仍仅在档案册中" : "character file(s) remain archive-only"}</li></ul></StickyNote>
      </header>

      {error && <Toast tone="danger" title={zh ? "角色档案读取失败" : "Character files unavailable"}>{error}</Toast>}
      {portraitMessage && <Toast tone="success" title={zh ? "角色图片已更新" : "Portrait updated"}>{portraitMessage}</Toast>}

      <section className="character-archive-summary" aria-label={zh ? "角色档案统计" : "Character archive summary"}>
        <div className="character-archive-total"><FunctionalIcon name="archive" size={36} /><strong>{archiveCounts.all}</strong><span>{zh ? "角色档案" : "Character Files"}<small>{zh ? "角色档案总数" : "filed in this workspace"}</small></span></div>
        {!demoMode && <Button variant="primary" size="lg" onClick={onCreate}>＋ {zh ? "创建新角色" : "Create Character"}</Button>}
        <SearchField value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder={zh ? "找角色…" : "Find a character…"} label={t("shelf.search")} />
      </section>

      {cards.length === 0 ? <EmptyState className="empty-library paper-sheet" illustration={<img src="/assets/brand/character-relay-mark.png" alt="" />} title={t("shelf.emptyTitle")} description={t("shelf.emptyHelp")} action={!demoMode ? <Button variant="primary" onClick={onCreate}>{t("shelf.newCard")}</Button> : undefined} /> : <>
        <section className="character-archive-toolbar">
          <PageFlagGroup orientation="horizontal" label={zh ? "角色档案筛选" : "Character archive filters"}>{archiveFilters.map((filter) => <PageFlag key={filter.id} tone={filter.tone} active={archiveFilter === filter.id} onClick={() => setArchiveFilter(filter.id)}><FunctionalIcon name={filter.icon} size={22} /><span className="character-archive-filter-copy"><strong>{zh ? filter.zh : filter.en}</strong><small>{zh ? filter.zhSubtitle : filter.enSubtitle}</small></span></PageFlag>)}</PageFlagGroup>
        </section>

        <div className="character-archive-book">
          <section className="character-archive-files" aria-label={t("shelf.cardsAria")}>
            {pageCards.map((card, index) => {
              const cardDeployments = deploymentsByCard.get(card.id) ?? [];
              const needsSetup = !targetById.has(card.target_id);
              const active = cardDeployments.filter((item) => item.status === "active").length;
              return <article className={`character-archive-card portrait-${card.portrait_variant}`} key={card.id}>
                <div className="character-archive-card-index">FILE {String((page - 1) * PAGE_SIZE + index + 1).padStart(2, "0")}</div>
                <button type="button" className="character-archive-card-cover" onClick={() => onOpenFile(card)} aria-label={`${zh ? "打开档案" : "Open file"}: ${card.display_name}`}>
                  <div className="character-archive-card-lead"><div className="character-archive-portrait"><CharacterPortrait cardId={card.id} version={portraitVersions[card.id] ?? 0} alt={card.display_name} /></div><div className="character-archive-card-copy"><h2>{card.display_name}</h2><p>{card.subtitle || t(subjectKeys[card.subject_type])}</p></div></div>
                  <p className="character-archive-card-summary">{card.persona_summary || (zh ? "尚未填写人物摘要。" : "No persona summary has been filed.")}</p>
                  <div className="character-archive-card-tags">{card.traits.slice(0, 3).map((trait) => <StickyLabel variant="neutral" key={trait}>{trait}</StickyLabel>)}</div>
                </button>
                <div className="character-archive-card-status"><StickyLabel variant={needsSetup ? "danger" : active > 0 ? "success" : cardDeployments.length > 0 ? "warning" : "neutral"}>{needsSetup ? (zh ? "需要设置" : "Needs setup") : active > 0 ? (zh ? `${active} 个活跃部署` : `${active} active`) : cardDeployments.length > 0 ? (zh ? "已有部署" : "Deployed") : (zh ? "未部署" : "Not deployed")}</StickyLabel></div>
                <div className="character-archive-card-actions"><Button variant="primary" onClick={() => onOpenFile(card)}>{zh ? "打开档案" : "Open File"} →</Button></div>
              </article>;
            })}
            {!demoMode && page === pageCount && <button className="character-archive-new-file" onClick={onCreate}><img src="/assets/brand/character-relay-mark.png" alt="" /><strong>{zh ? "新建角色档案" : "New Character File"}</strong><small>{zh ? "开始书写" : "Start writing"}</small><span>＋</span></button>}
          </section>

          <aside className="character-archive-margin">
            <StickyNote variant="reminder" size="md" pinned><strong>{zh ? "设置笔记" : "SETUP NOTES"}</strong><p>{zh ? "打开角色档案可查看角色的完整记录：" : "Open a Character File to inspect its full record:"}</p><ul><li>Profile</li><li>Prompt</li><li>Memory</li><li>Runtime</li></ul></StickyNote>
          </aside>
        </div>

        <div className="character-archive-tip"><FunctionalIcon name="review" size={18} /><span>{zh ? "提示：定期更新角色的记忆与提示词，让他们保持最佳状态。" : "Tip: revisit memory and prompts regularly to keep each character coherent."}</span></div>
        <footer className="character-archive-system-note"><strong><FunctionalIcon name="archive" size={17} /> SYSTEM NOTE</strong><span><i />{zh ? "档案已就绪" : "Archive ready"}</span><span><i />{filtered.length} {zh ? "个当前结果" : "current result(s)"}</span><span>{cards.length} {zh ? "个角色档案" : "file(s) in archive"}</span></footer>

        {filtered.length === 0 && <EmptyState className="no-results paper-sheet" title={t("shelf.noResults")} description={t("shelf.noResultsHelp")} action={<Button variant="secondary" onClick={() => { setQuery(""); setArchiveFilter("all"); }}>{zh ? "清除筛选" : "Clear filters"}</Button>} />}
        {pageCount > 1 && <nav className="library-pagination" aria-label={t("shelf.pagination")}><Button variant="secondary" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>{t("shelf.previous")}</Button><span>{t("shelf.page", { page, pages: pageCount })}</span><Button variant="secondary" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page === pageCount}>{t("shelf.next")}</Button></nav>}
      </>}
    </main>
  );
}
