import { useEffect, useState } from "react";

import type { CharacterCard } from "./api";
import { ConversationStructurePanel } from "./ConversationStructurePanel";
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
import type { IntelligenceWorkspaceTab } from "./portalRoutes";
import "./intelligence-product-completion.css";

interface Props {
  cards: CharacterCard[];
  profile: DiscordServerProfile;
  catalog?: DiscordServerCatalog;
  zh: boolean;
  activeTab?: IntelligenceWorkspaceTab;
  onTabChange?: (tab: IntelligenceWorkspaceTab) => void;
}

export function ConversationIntelligenceInspector({
  cards,
  profile,
  zh,
  activeTab,
  onTabChange
}: Props) {
  const [localWorkspaceTab, setLocalWorkspaceTab] = useState<IntelligenceWorkspaceTab>("presence");
  const workspaceTab = activeTab ?? localWorkspaceTab;
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

  function selectWorkspaceTab(next: IntelligenceWorkspaceTab) {
    if (onTabChange) onTabChange(next);
    else setLocalWorkspaceTab(next);
  }

  const tabs: Array<{ key: IntelligenceWorkspaceTab; en: string; zh: string }> = [
    { key: "presence", en: "Live Presence", zh: "当前状态" },
    { key: "social", en: "Social", zh: "关系 / 看法" },
    { key: "participation", en: "Participation", zh: "参与判断" },
    { key: "conversation", en: "Conversation", zh: "对话结构" },
    { key: "discovery", en: "Discovery", zh: "探索记录" }
  ];

  return (
    <section className="intelligence-workspace-shell intelligence-product-workspace">
      <header className="intelligence-workspace-header paper-sheet">
        <div>
          <span className="tape-label">INTELLIGENCE WORKSPACE</span>
          <strong>{zh ? "Server Intelligence / 运行监测" : "Server Intelligence / Runtime Observatory"}</strong>
          <small>
            {zh
              ? "Intelligence 统一观察 Presence、Social、Participation、Conversation 与 Discovery。Conversation Authority v3 已取代旧 Topic routing。"
              : "Intelligence observes Presence, Social state, Participation, Conversation, and Discovery. Conversation Authority v3 replaces legacy Topic routing."}
          </small>
        </div>
        <button
          type="button"
          className="paper-button"
          disabled={loading}
          onClick={() => void loadDeployments()}
        >
          {zh ? "刷新角色" : "Refresh Characters"}
        </button>
      </header>

      <nav
        className="intelligence-workspace-tabs intelligence-product-tabs"
        aria-label={zh ? "Intelligence 页面" : "Intelligence pages"}
      >
        {tabs.map((item) => (
          <button
            type="button"
            key={item.key}
            className={workspaceTab === item.key ? "is-active" : ""}
            onClick={() => selectWorkspaceTab(item.key)}
          >
            {zh ? item.zh : item.en}
          </button>
        ))}
      </nav>

      {error && (
        <section className="paper-sheet intelligence-workspace-empty error-note">{error}</section>
      )}

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
        <ConversationStructurePanel deployments={deployments} zh={zh} />
      )}

      {workspaceTab === "discovery" && (
        <DiscoveryIntelligencePanel deployments={deployments} zh={zh} />
      )}
    </section>
  );
}
