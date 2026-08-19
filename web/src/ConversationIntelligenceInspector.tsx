import { useEffect, useState } from "react";

import type { CharacterCard } from "./api";
import { ConversationStructurePanel } from "./ConversationStructurePanel";
import { ConversationIntelligenceInspector as CharacterIntelligenceInspector } from "./ConversationIntelligenceInspectorLegacy";
import {
  deploymentApi,
  type CharacterDeployment,
  type DiscordServerCatalog,
  type DiscordServerProfile
} from "./deploymentApi";
import { DeploymentPresencePanel } from "./DeploymentPresencePanel";
import { DiscoveryIntelligencePanel } from "./DiscoveryIntelligencePanel";
import { ParticipationIntelligencePanel } from "./ParticipationIntelligencePanel";
import { SocialIntelligencePanel } from "./SocialIntelligencePanel";
import "./intelligence-product-completion.css";
import "./stabilization-hotfix.css";

interface Props {
  cards: CharacterCard[];
  profile: DiscordServerProfile;
  catalog?: DiscordServerCatalog;
  zh: boolean;
}

type IntelligenceWorkspaceTab =
  | "presence"
  | "social"
  | "participation"
  | "conversation"
  | "discovery"
  | "data";

export function ConversationIntelligenceInspector({ cards, profile, catalog, zh }: Props) {
  const [workspaceTab, setWorkspaceTab] = useState<IntelligenceWorkspaceTab>("presence");
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDeployments() {
    try {
      setLoading(true);
      setError("");
      setDeployments(await deploymentApi.listDeploymentsForServer(profile.id));
    } catch (reason) {
      setDeployments([]);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDeployments();
  }, [profile.id]);

  const tabs: Array<{ key: IntelligenceWorkspaceTab; en: string; zh: string }> = [
    { key: "presence", en: "Live Presence", zh: "当前状态" },
    { key: "social", en: "Social", zh: "关系 / 看法" },
    { key: "participation", en: "Participation", zh: "参与判断" },
    { key: "conversation", en: "Conversation", zh: "对话结构" },
    { key: "discovery", en: "Discovery", zh: "探索记录" },
    { key: "data", en: "Character Data", zh: "角色数据" }
  ];

  return (
    <section className="intelligence-workspace-shell intelligence-product-workspace">
      <header className="intelligence-workspace-header paper-sheet">
        <div>
          <span className="tape-label">INTELLIGENCE WORKSPACE</span>
          <strong>{zh ? "Server Intelligence / 运行监测" : "Server Intelligence / Runtime Observatory"}</strong>
          <small>
            {zh
              ? "Intelligence 统一观察角色 Presence、Social、Participation、Conversation 与 Discovery；Deployment Editor 只负责修改运行权限和配置。"
              : "Intelligence is the shared observatory for Presence, Social state, Participation, Conversation, and Discovery. Deployment Editor only changes runtime policy and configuration."}
          </small>
        </div>
        <button type="button" className="paper-button" disabled={loading} onClick={() => void loadDeployments()}>
          {zh ? "刷新角色" : "Refresh Characters"}
        </button>
      </header>

      <nav className="intelligence-workspace-tabs intelligence-product-tabs" aria-label={zh ? "Intelligence 页面" : "Intelligence pages"}>
        {tabs.map((item) => (
          <button
            type="button"
            key={item.key}
            className={workspaceTab === item.key ? "is-active" : ""}
            onClick={() => setWorkspaceTab(item.key)}
          >
            {zh ? item.zh : item.en}
          </button>
        ))}
      </nav>

      {error && <section className="paper-sheet intelligence-workspace-empty error-note">{error}</section>}

      {workspaceTab === "presence" && (
        <DeploymentPresencePanel serverProfileId={profile.id} zh={zh} />
      )}

      {workspaceTab === "social" && (
        <SocialIntelligencePanel cards={cards} deployments={deployments} zh={zh} />
      )}

      {workspaceTab === "participation" && (
        <ParticipationIntelligencePanel serverProfileId={profile.id} zh={zh} />
      )}

      {workspaceTab === "conversation" && (
        <ConversationStructurePanel serverProfileId={profile.id} zh={zh} />
      )}

      {workspaceTab === "discovery" && (
        <DiscoveryIntelligencePanel deployments={deployments} zh={zh} />
      )}

      {workspaceTab === "data" && (
        <section className="intelligence-legacy-compat">
          <div className="paper-sheet intelligence-compat-note">
            <strong>{zh ? "兼容数据视图" : "Compatibility data view"}</strong>
            <p>
              {zh
                ? "这里保留 Memory、Character Mind、Data Hygiene 与旧 Topic/Social 派生证据用于迁移和审计。当前 routing authority 是上方的 Conversation / Semantic Threads，当前关系 authority 是 Social Intelligence v2。"
                : "This area retains Memory, Character Mind, Data Hygiene, and legacy Topic/Social derived evidence for migration and audit. Current routing authority is Conversation / Semantic Threads above, and current relationship authority is Social Intelligence v2."}
            </p>
          </div>
          <CharacterIntelligenceInspector
            cards={cards}
            profile={profile}
            catalog={catalog}
            zh={zh}
          />
        </section>
      )}
    </section>
  );
}
