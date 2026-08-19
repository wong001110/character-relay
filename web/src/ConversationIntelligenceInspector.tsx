import { useEffect, useState } from "react";

import type { CharacterCard } from "./api";
import { ConversationStructurePanel } from "./ConversationStructurePanel";
import { ConversationIntelligenceInspector as CharacterIntelligenceInspector } from "./ConversationIntelligenceInspectorLegacy";
import {
  deploymentApi,
  type DiscordServerCatalog,
  type DiscordServerProfile
} from "./deploymentApi";
import { DeploymentPresencePanel } from "./DeploymentPresencePanel";
import "./stabilization-hotfix.css";

interface Props {
  cards: CharacterCard[];
  profile: DiscordServerProfile;
  catalog?: DiscordServerCatalog;
  zh: boolean;
}

type IntelligenceWorkspaceTab = "presence" | "character" | "conversation";

export function ConversationIntelligenceInspector({ cards, profile, catalog, zh }: Props) {
  const [workspaceTab, setWorkspaceTab] = useState<IntelligenceWorkspaceTab>("presence");
  const [conversationDeploymentId, setConversationDeploymentId] = useState("");
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationError, setConversationError] = useState("");

  useEffect(() => {
    let active = true;
    setConversationLoading(true);
    setConversationError("");
    deploymentApi
      .listDeploymentsForServer(profile.id)
      .then((items) => {
        if (!active) return;
        const preferred = items.find((item) => item.status === "active") ?? items[0];
        setConversationDeploymentId(preferred?.id ?? "");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setConversationDeploymentId("");
        setConversationError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setConversationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [profile.id]);

  return (
    <section className="intelligence-workspace-shell">
      <header className="intelligence-workspace-header paper-sheet">
        <div>
          <span className="tape-label">INTELLIGENCE WORKSPACE</span>
          <strong>{zh ? "Server Intelligence / 运行监测" : "Server Intelligence / Runtime Observatory"}</strong>
          <small>
            {zh
              ? "Intelligence 统一观察角色当前状态、学习状态与 Server 对话结构；Deployment Editor 只负责修改 Deployment 配置。"
              : "Intelligence is the shared observatory for live Character Presence, learned state, and Server conversation structure. Deployment Editor only changes Deployment configuration."}
          </small>
        </div>
        <nav className="intelligence-workspace-tabs" aria-label={zh ? "Intelligence 页面" : "Intelligence pages"}>
          <button
            type="button"
            className={workspaceTab === "presence" ? "is-active" : ""}
            onClick={() => setWorkspaceTab("presence")}
          >
            {zh ? "当前状态" : "Live Presence"}
          </button>
          <button
            type="button"
            className={workspaceTab === "character" ? "is-active" : ""}
            onClick={() => setWorkspaceTab("character")}
          >
            {zh ? "角色 Intelligence" : "Character Intelligence"}
          </button>
          <button
            type="button"
            className={workspaceTab === "conversation" ? "is-active" : ""}
            onClick={() => setWorkspaceTab("conversation")}
          >
            {zh ? "对话结构" : "Conversation Structure"}
          </button>
        </nav>
      </header>

      {workspaceTab === "presence" ? (
        <DeploymentPresencePanel serverProfileId={profile.id} zh={zh} />
      ) : workspaceTab === "character" ? (
        <CharacterIntelligenceInspector
          cards={cards}
          profile={profile}
          catalog={catalog}
          zh={zh}
        />
      ) : conversationLoading ? (
        <section className="paper-sheet intelligence-workspace-empty">
          {zh ? "正在读取 Server Conversation Structure…" : "Loading Server Conversation Structure…"}
        </section>
      ) : conversationError ? (
        <section className="paper-sheet intelligence-workspace-empty error-note">
          {conversationError}
        </section>
      ) : conversationDeploymentId ? (
        <ConversationStructurePanel deploymentId={conversationDeploymentId} zh={zh} />
      ) : (
        <section className="paper-sheet intelligence-workspace-empty">
          <strong>{zh ? "这个 Server 还没有 Character Deployment" : "No Character Deployment in this Server yet"}</strong>
          <p>
            {zh
              ? "Conversation Structure 是 Server 范围的运行证据；建立至少一个 Deployment 后即可在这里观察 Burst、Segment 与 Semantic Thread。"
              : "Conversation Structure is Server-scoped runtime evidence. Add at least one Deployment to inspect Bursts, Segments, and Semantic Threads here."}
          </p>
        </section>
      )}
    </section>
  );
}
