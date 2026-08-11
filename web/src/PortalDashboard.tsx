import type { CharacterCard, RuntimeStatus } from "./api";
import { useI18n } from "./i18n";
import type { PortalSection } from "./PortalShell";

interface Props {
  cards: CharacterCard[];
  runtime: RuntimeStatus | null;
  onNavigate: (section: PortalSection) => void;
  onCreateCharacter: () => void;
}

export function PortalDashboard({
  cards,
  runtime,
  onNavigate,
  onCreateCharacter
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const configuredRuntimes = [runtime?.adaptive, runtime?.judge].filter(
    (item) => item?.enabled && item.configured
  ).length;

  return (
    <main className="portal-v2-dashboard">
      <section className="portal-v2-dashboard-hero">
        <div className="portal-v2-hero-copy">
          <span className="portal-v2-tape">CHARACTER RESEARCH STUDIO</span>
          <h1>{zh ? "今天想让谁去真实世界里说话？" : "Who should step into a real conversation today?"}</h1>
          <p>
            {zh
              ? "从角色档案、Discord 部署、实验测试到行为观察，都放在同一本 Character Relay 研究手帐里。"
              : "Character files, Discord deployments, experiments, and behavior observations now live in one Character Relay research notebook."}
          </p>
          <div className="portal-v2-hero-actions">
            <button className="ink-button" onClick={onCreateCharacter}>
              {zh ? "+ 创建角色" : "+ Create character"}
            </button>
            <button className="paper-button" onClick={() => onNavigate("toolbox")}>
              {zh ? "打开行为观察" : "Open behavior observer"}
            </button>
          </div>
        </div>
        <aside className="portal-v2-hero-note">
          <span>STUDIO NOTE</span>
          <strong>{cards.length}</strong>
          <p>{zh ? "个角色档案" : "character files"}</p>
          <small>
            {configuredRuntimes > 0
              ? zh
                ? `${configuredRuntimes} 个评测 Runtime 已配置`
                : `${configuredRuntimes} evaluation runtimes configured`
              : zh
                ? "评测 Runtime 可在设置中配置"
                : "Evaluation runtimes can be configured in Settings"}
          </small>
          <span className="portal-v2-note-cat" aria-hidden="true">=^･ω･^=</span>
        </aside>
      </section>

      <section className="portal-v2-dashboard-grid">
        <button className="portal-v2-dashboard-card accent-lavender" onClick={() => onNavigate("characters")}>
          <span className="portal-v2-card-index">01 / CHARACTER FILES</span>
          <strong>{zh ? "角色档案册" : "Character files"}</strong>
          <p>{zh ? "编辑 Persona、Prompt、记忆边界与参与方式。" : "Shape persona, prompts, memory boundaries, and participation behavior."}</p>
          <span className="portal-v2-card-arrow">→</span>
        </button>

        <button className="portal-v2-dashboard-card accent-mint" onClick={() => onNavigate("deployments")}>
          <span className="portal-v2-card-index">02 / REAL WORLD</span>
          <strong>{zh ? "Discord 部署板" : "Discord deployment board"}</strong>
          <p>{zh ? "把角色送进 Server，并管理身份、Channel、Tools 与 Smart Participation。" : "Send characters into servers and manage identity, channels, tools, and Smart Participation."}</p>
          <span className="portal-v2-card-arrow">→</span>
        </button>

        <button className="portal-v2-dashboard-card accent-peach" onClick={() => onNavigate("toolbox")}>
          <span className="portal-v2-card-index">03 / NOTEBOOK</span>
          <strong>{zh ? "行为观察手帐" : "Behavior notebook"}</strong>
          <p>{zh ? "把 LangGraph、Provider、Tool 和 Media 的执行证据整理成可读的行为记录。" : "Turn LangGraph, provider, tool, and media evidence into a readable behavior record."}</p>
          <span className="portal-v2-card-arrow">→</span>
        </button>

        <button className="portal-v2-dashboard-card accent-rose" onClick={() => onNavigate("settings")}>
          <span className="portal-v2-card-index">04 / SETTINGS</span>
          <strong>{zh ? "账户与 Runtime" : "Account & runtime"}</strong>
          <p>{zh ? "管理账户、安全、Provider Key 与系统级配置。" : "Manage account security, provider credentials, and system-level configuration."}</p>
          <span className="portal-v2-card-arrow">→</span>
        </button>
      </section>

      <section className="portal-v2-dashboard-strip">
        <div>
          <span>{zh ? "工作流" : "Workflow"}</span>
          <strong>{zh ? "创作 → 测试 → 部署 → 观察 → 调整" : "Create → Test → Deploy → Observe → Refine"}</strong>
        </div>
        <p>{zh ? "Character Relay 不是传统企业后台，而是一间 AI 角色研究室。" : "Character Relay is an AI character studio, not a conventional enterprise admin console."}</p>
      </section>
    </main>
  );
}
