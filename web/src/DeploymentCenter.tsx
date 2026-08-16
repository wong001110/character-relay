import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { CharacterCard } from "./api";
import {
  deploymentApi,
  type CharacterDeployment,
  type ConnectionMode,
  type DeploymentStatus,
  type DiscordCatalogChannel,
  type DiscordServerCatalog,
  type DiscordServerProfile,
  type MemoryScope,
  type ParticipationMode,
  type PlatformConnection,
  type PlatformId
} from "./deploymentApi";
import { DeploymentToolSelector } from "./DeploymentToolSelector";
import {
  discordIdentityApi,
  type DeploymentIdentityMode,
  type DeploymentMessageIdentity
} from "./discordIdentityApi";
import { ConversationIntelligenceInspector } from "./ConversationIntelligenceInspector";
import { CharacterPortrait } from "./CharacterPortrait";
import { DiscordEventLogPanel } from "./DiscordEventLogPanel";
import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";
import { PaperDrawer, PaperModal } from "./NotebookUI";
import { Pagination } from "./Pagination";
import { useI18n } from "./i18n";
import { InteractionSessionsPanel } from "./InteractionSessionsPanel";
import { KnowledgeBasePanel } from "./KnowledgeBasePanel";
import { SmartParticipationStudio } from "./SmartParticipationStudio";
import { serverRuntimeApi } from "./serverRuntimeApi";

interface Props {
  cards: CharacterCard[];
  initialCharacterId?: string | null;
  demoMode?: boolean;
  onClose: () => void;
}

interface ChannelGroup {
  id: string;
  name: string;
  channels: DiscordCatalogChannel[];
}

type ServerNotebookTab = "characters" | "knowledge" | "interactions" | "intelligence";

const platformLabels: Record<PlatformId, string> = {
  discord: "Discord",
  whatsapp: "WhatsApp",
  telegram: "Telegram"
};

const platformNotes: Record<PlatformId, { en: string; zh: string }> = {
  discord: {
    en: "Managed Gateway connector with reusable server profiles and per-character webhook identities.",
    zh: "托管式 Gateway Connector，支持可复用 Server 配置与角色 Webhook 身份。"
  },
  whatsapp: {
    en: "Local experimental connector. The linked-device session stays on the user's computer.",
    zh: "本地实验 Connector，Linked Device Session 保留在用户电脑。"
  },
  telegram: {
    en: "Managed Bot connector with native group and sticker support.",
    zh: "托管式 Bot Connector，支持群组与原生贴图。"
  }
};

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function participationLabel(mode: ParticipationMode, zh: boolean): string {
  const labels: Record<ParticipationMode, { en: string; zh: string }> = {
    mention_only: { en: "Mention only", zh: "仅被提及时" },
    reply_only: { en: "Reply only", zh: "仅回复消息时" },
    mention_and_reply: { en: "Mention + reply", zh: "提及或回复时" },
    smart: { en: "Smart participation", zh: "智能参与" }
  };
  return zh ? labels[mode].zh : labels[mode].en;
}

function participationHelp(mode: ParticipationMode, zh: boolean): string {
  const help: Record<ParticipationMode, { en: string; zh: string }> = {
    mention_only: {
      en: "Respond only when the Character is explicitly mentioned.",
      zh: "只有明确提及该角色时才回应。"
    },
    reply_only: {
      en: "Respond only when someone replies to the Character's message.",
      zh: "只有回复该角色的消息时才回应。"
    },
    mention_and_reply: {
      en: "Respond to explicit mentions and direct replies.",
      zh: "明确提及或直接回复时回应。"
    },
    smart: {
      en: "Let Smart Participation decide from the current conversation context.",
      zh: "由 Smart Participation 根据当前对话语境决定是否参与。"
    }
  };
  return zh ? help[mode].zh : help[mode].en;
}

function memoryLabel(scope: MemoryScope, zh: boolean): string {
  const labels: Record<MemoryScope, { en: string; zh: string }> = {
    channel_isolated: { en: "Channel isolated", zh: "Channel 隔离" },
    server_shared: { en: "Server shared", zh: "Server 共享" },
    custom: { en: "Custom", zh: "自定义" }
  };
  return zh ? labels[scope].zh : labels[scope].en;
}

function activityLabel(value: string | null, zh: boolean): string {
  if (!value) return zh ? "尚无消息活动" : "No message activity yet";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(timestamp);
}

function destination(deployment: CharacterDeployment, zh: boolean): string {
  const workspace = deployment.workspace_name || platformLabels[deployment.platform];
  if (deployment.channel_scope_mode === "all_except") {
    const excluded =
      deployment.excluded_channel_ids.length + deployment.excluded_category_ids.length;
    return `${workspace} / ${zh ? "全部 Channel，额外排除" : "All channels, additionally excluding"} ${excluded}`;
  }
  const channel = deployment.channel_name || deployment.channel_id;
  return deployment.thread_name
    ? `${workspace} / ${channel} / ${deployment.thread_name}`
    : `${workspace} / ${channel}`;
}

function defaultIdentity(deployment: CharacterDeployment): DeploymentMessageIdentity {
  const webhook = deployment.platform === "discord";
  return {
    deployment_id: deployment.id,
    mode: webhook ? "webhook" : "bot",
    display_name: deployment.character_display_name,
    avatar_url: "",
    address_aliases: inferredAddressAliases(deployment.character_display_name),
    webhook_status: webhook ? "pending" : "not_required",
    last_error: "",
    updated_at: deployment.updated_at
  };
}

function connectorDisplayName(connection: PlatformConnection): string {
  const value = connection.metadata.connector_display_name;
  return typeof value === "string" ? value : "";
}

function inferredAddressAliases(...values: string[]): string[] {
  const aliases: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const full = value.trim();
    if (!full) continue;
    const normalized = full
      .replaceAll(/[（(]/gu, " · ")
      .replaceAll(/[）)]/gu, "");
    for (const candidate of [
      full,
      ...normalized.split(/\s*(?:·|•|・|／|\/|\||｜)\s*|\s+(?:-|—|–)\s+/u)
    ]) {
      const alias = candidate.trim();
      const key = alias.toLocaleLowerCase();
      if (!alias || seen.has(key)) continue;
      seen.add(key);
      aliases.push(alias);
    }
  }
  return aliases.slice(0, 20);
}

function channelGroups(server: DiscordServerCatalog | undefined): ChannelGroup[] {
  if (!server) return [];
  const groups = new Map<string, ChannelGroup>();
  for (const channel of server.channels) {
    const key = channel.category_id || "@uncategorized";
    const current = groups.get(key) ?? {
      id: channel.category_id,
      name: channel.category_name || "Uncategorized",
      channels: []
    };
    current.channels.push(channel);
    groups.set(key, current);
  }
  return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function toggleSet(
  current: Set<string>,
  value: string,
  setter: (value: Set<string>) => void
) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  setter(next);
}

export function DeploymentCenter({
  cards,
  initialCharacterId = null,
  demoMode = false,
  onClose
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [serverProfiles, setServerProfiles] = useState<DiscordServerProfile[]>([]);
  const [serverCatalog, setServerCatalog] = useState<DiscordServerCatalog[]>([]);
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [deploymentPage, setDeploymentPage] = useState(1);
  const [deploymentPages, setDeploymentPages] = useState(1);
  const [deploymentTotal, setDeploymentTotal] = useState(0);
  const [deploymentCounts, setDeploymentCounts] = useState({
    active: 0,
    paused: 0,
    attention: 0
  });
  const [identities, setIdentities] = useState<DeploymentMessageIdentity[]>([]);
  const [deploymentTools, setDeploymentTools] = useState<Record<string, string[]>>({});
  const [serverTimezone, setServerTimezone] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedServerProfileId, setSelectedServerProfileId] = useState(() =>
    new URLSearchParams(window.location.search).get("server_profile") ?? ""
  );
  const serverSelectionInitialized = useRef(false);

  const [connectionOpen, setConnectionOpen] = useState(false);
  const [connectionManagerOpen, setConnectionManagerOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<PlatformConnection | null>(null);
  const [connectionPlatform, setConnectionPlatform] = useState<PlatformId>("discord");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("managed");

  const [deploymentOpen, setDeploymentOpen] = useState(Boolean(initialCharacterId));
  const [eventLogOpen, setEventLogOpen] = useState(false);
  const [editingDeployment, setEditingDeployment] = useState<CharacterDeployment | null>(null);
  const [draftCharacterId, setDraftCharacterId] = useState(
    initialCharacterId ?? cards[0]?.id ?? ""
  );
  const [draftConnectionId, setDraftConnectionId] = useState("");
  const [draftServerProfileId, setDraftServerProfileId] = useState("");
  const [draftParticipationMode, setDraftParticipationMode] =
    useState<ParticipationMode>("mention_and_reply");
  const [excludedChannels, setExcludedChannels] = useState<Set<string>>(new Set());
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());

  const [statusFilter, setStatusFilter] = useState<"all" | DeploymentStatus>("all");
  const [characterFilter, setCharacterFilter] = useState(initialCharacterId ?? "all");
  const [serverNotebookTab, setServerNotebookTab] = useState<ServerNotebookTab>("characters");

  async function load(page = deploymentPage) {
    try {
      setLoading(true);
      const [
        nextConnections,
        nextProfiles,
        nextCatalog,
        nextDeployments,
        nextIdentities
      ] = await Promise.all([
        deploymentApi.listConnections(),
        deploymentApi.listDiscordServerProfiles(),
        deploymentApi.listDiscordServerCatalog(),
        deploymentApi.listDeploymentsPage({
          page,
          pageSize: 20,
          characterCardId: characterFilter,
          platform: "discord",
          status: statusFilter,
          serverProfileId: selectedServerProfileId || "__no_server_selected__"
        }),
        discordIdentityApi.list()
      ]);
      setConnections(nextConnections);
      setServerProfiles(nextProfiles);
      setServerCatalog(nextCatalog);
      setSelectedServerProfileId((current) =>
        current && nextProfiles.some((item) => item.id === current)
          ? current
          : nextProfiles[0]?.id ?? ""
      );
      setDeployments(nextDeployments.items);
      setDeploymentPage(nextDeployments.page);
      setDeploymentPages(nextDeployments.pages);
      setDeploymentTotal(nextDeployments.total);
      setDeploymentCounts({
        active: nextDeployments.active,
        paused: nextDeployments.paused,
        attention: nextDeployments.attention
      });
      setIdentities(nextIdentities);
      const toolProfiles = await Promise.allSettled(
        nextDeployments.items.map((item) => deploymentApi.getDeploymentTools(item.id))
      );
      setDeploymentTools(
        Object.fromEntries(
          toolProfiles.flatMap((result, index) =>
            result.status === "fulfilled"
              ? [[nextDeployments.items[index].id, result.value.enabled_tools] as const]
              : []
          )
        )
      );
      setDraftConnectionId((current) =>
        current && nextConnections.some((item) => item.id === current)
          ? current
          : nextConnections[0]?.id ?? ""
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(1);
  }, [characterFilter, selectedServerProfileId, statusFilter]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedServerProfileId) url.searchParams.set("server_profile", selectedServerProfileId);
    else url.searchParams.delete("server_profile");
    window.history.replaceState({}, "", url);
    if (serverSelectionInitialized.current) {
      setDeploymentOpen(false);
      setEditingDeployment(null);
    }
    if (selectedServerProfileId) serverSelectionInitialized.current = true;
    setDeploymentPage(1);
  }, [selectedServerProfileId]);

  useEffect(() => {
    if (!selectedServerProfileId && serverNotebookTab !== "characters") {
      setServerNotebookTab("characters");
    }
  }, [selectedServerProfileId, serverNotebookTab]);

  useEffect(() => {
    let active = true;
    setServerTimezone(null);
    if (!selectedServerProfileId) return () => { active = false; };
    serverRuntimeApi.getTimezone(selectedServerProfileId)
      .then((runtime) => {
        if (active) setServerTimezone(runtime.timezone);
      })
      .catch(() => {
        if (active) setServerTimezone(null);
      });
    return () => { active = false; };
  }, [selectedServerProfileId]);

  useEffect(() => {
    if (!initialCharacterId) return;
    setCharacterFilter(initialCharacterId);
    setDraftCharacterId(initialCharacterId);
    setServerNotebookTab("characters");
    setDeploymentOpen(true);
  }, [initialCharacterId]);

  useEffect(() => {
    if (editingDeployment) return;
    const connection = connections.find((item) => item.id === draftConnectionId);
    if (connection?.platform !== "discord") {
      setDraftServerProfileId("");
      return;
    }
    const valid = serverProfiles.some(
      (profile) =>
        profile.id === draftServerProfileId && profile.connection_id === draftConnectionId
    );
    if (!valid) {
      setDraftServerProfileId(
        serverProfiles.find((profile) => profile.connection_id === draftConnectionId)?.id ?? ""
      );
      setExcludedChannels(new Set());
      setExcludedCategories(new Set());
    }
  }, [connections, draftConnectionId, draftServerProfileId, editingDeployment, serverProfiles]);

  const identityMap = useMemo(
    () => new Map(identities.map((item) => [item.deployment_id, item])),
    [identities]
  );
  const profileMap = useMemo(
    () => new Map(serverProfiles.map((profile) => [profile.id, profile])),
    [serverProfiles]
  );
  const cardMap = useMemo(
    () => new Map(cards.map((card) => [card.id, card])),
    [cards]
  );

  const selectedWorkspaceProfile = profileMap.get(selectedServerProfileId);
  const selectedWorkspaceCatalog = selectedWorkspaceProfile
    ? serverCatalog.find(
        (server) =>
          server.connection_id === selectedWorkspaceProfile.connection_id &&
          server.guild_id === selectedWorkspaceProfile.guild_id
      )
    : undefined;
  const selectedWorkspaceConnection = selectedWorkspaceProfile
    ? connections.find((item) => item.id === selectedWorkspaceProfile.connection_id)
    : undefined;

  useEffect(() => {
    if (!selectedWorkspaceProfile || editingDeployment) return;
    setDraftConnectionId(selectedWorkspaceProfile.connection_id);
    setDraftServerProfileId(selectedWorkspaceProfile.id);
  }, [
    editingDeployment,
    selectedWorkspaceProfile?.connection_id,
    selectedWorkspaceProfile?.id
  ]);

  const selectedConnection = connections.find((item) => item.id === draftConnectionId);
  const connectionProfiles = serverProfiles.filter(
    (profile) => profile.connection_id === draftConnectionId
  );
  const selectedProfile = profileMap.get(draftServerProfileId);
  const selectedCatalog = selectedProfile
    ? serverCatalog.find(
        (server) =>
          server.connection_id === selectedProfile.connection_id &&
          server.guild_id === selectedProfile.guild_id
      )
    : undefined;
  const deploymentChannelGroups = useMemo(
    () => channelGroups(selectedCatalog),
    [selectedCatalog]
  );
  const formIdentity = editingDeployment
    ? identityMap.get(editingDeployment.id) ?? defaultIdentity(editingDeployment)
    : null;
  const formConnection = editingDeployment
    ? connections.find((item) => item.id === editingDeployment.connection_id)
    : selectedConnection;
  const discordIdentityEnabled = formConnection?.platform === "discord";
  const isLegacyExactDiscord =
    editingDeployment?.platform === "discord" &&
    editingDeployment.channel_scope_mode === "exact" &&
    !draftServerProfileId;
  const globallyExcludedChannels = new Set(selectedProfile?.excluded_channel_ids ?? []);
  const globallyExcludedCategories = new Set(selectedProfile?.excluded_category_ids ?? []);

  function changeConnectionPlatform(platform: PlatformId) {
    setConnectionPlatform(platform);
    setConnectionMode(platform === "whatsapp" ? "local" : "managed");
  }

  function openNewConnection() {
    setEditingConnection(null);
    setConnectionPlatform("discord");
    setConnectionMode("managed");
    setConnectionManagerOpen(true);
    setConnectionOpen(true);
  }

  function openConnectionManager() {
    setServerNotebookTab("characters");
    setConnectionManagerOpen(true);
  }

  function closeConnectionManager() {
    closeConnectionForm();
    setConnectionManagerOpen(false);
  }

  function openEditConnection(item: PlatformConnection) {
    setEditingConnection(item);
    setConnectionPlatform(item.platform);
    setConnectionMode(item.connection_mode);
    setConnectionOpen(true);
  }

  function closeConnectionForm() {
    setConnectionOpen(false);
    setEditingConnection(null);
  }

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const displayName = String(data.get("display_name") ?? "").trim();
    const externalAccountId = String(data.get("external_account_id") ?? "").trim();
    try {
      setWorking(true);
      setError(null);
      if (editingConnection) {
        await deploymentApi.updateConnection(editingConnection.id, {
          display_name: displayName,
          connection_mode: connectionMode,
          external_account_id: externalAccountId
        });
      } else {
        await deploymentApi.createConnection({
          platform: connectionPlatform,
          display_name: displayName,
          connection_mode: connectionMode,
          external_account_id: externalAccountId,
          status: "disconnected",
          metadata: {
            setup_state: "connector_not_configured",
            product_stage: "connector"
          }
        });
      }
      closeConnectionForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function openNewDeployment() {
    const connectionId = selectedWorkspaceProfile?.connection_id ?? "";
    if (!selectedWorkspaceProfile) return;
    setServerNotebookTab("characters");
    setEditingDeployment(null);
    setDraftCharacterId(initialCharacterId ?? cards[0]?.id ?? "");
    setDraftConnectionId(connectionId);
    setDraftServerProfileId(selectedWorkspaceProfile.id);
    setDraftParticipationMode("mention_and_reply");
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
    setDeploymentOpen(true);
  }

  function openEditDeployment(item: CharacterDeployment) {
    setServerNotebookTab("characters");
    setEditingDeployment(item);
    setDraftCharacterId(item.character_card_id);
    setDraftConnectionId(item.connection_id);
    setDraftServerProfileId(item.server_profile_id);
    setDraftParticipationMode(item.participation_mode);
    setExcludedChannels(new Set(item.excluded_channel_ids));
    setExcludedCategories(new Set(item.excluded_category_ids));
    setDeploymentOpen(true);
  }

  function closeDeploymentForm() {
    setDeploymentOpen(false);
    setEditingDeployment(null);
  }

  function changeDeploymentConnection(connectionId: string) {
    setDraftConnectionId(connectionId);
    setDraftServerProfileId(
      serverProfiles.find((profile) => profile.connection_id === connectionId)?.id ?? ""
    );
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
  }

  function changeServerProfile(profileId: string) {
    setDraftServerProfileId(profileId);
    setExcludedChannels(new Set());
    setExcludedCategories(new Set());
  }

  async function saveDeployment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const connection = connections.find((item) => item.id === draftConnectionId);
    const usesServerProfile = connection?.platform === "discord" && Boolean(draftServerProfileId);
    const baseFields = {
      server_profile_id: usesServerProfile ? draftServerProfileId : "",
      workspace_id: usesServerProfile
        ? ""
        : String(data.get("workspace_id") ?? "").trim(),
      workspace_name: usesServerProfile
        ? ""
        : String(data.get("workspace_name") ?? "").trim(),
      channel_id: usesServerProfile ? "" : String(data.get("channel_id") ?? "").trim(),
      channel_name: usesServerProfile
        ? ""
        : String(data.get("channel_name") ?? "").trim(),
      thread_id: usesServerProfile ? "" : String(data.get("thread_id") ?? "").trim(),
      thread_name: usesServerProfile
        ? ""
        : String(data.get("thread_name") ?? "").trim(),
      excluded_channel_ids: usesServerProfile ? [...excludedChannels] : [],
      excluded_category_ids: usesServerProfile ? [...excludedCategories] : [],
      participation_mode: draftParticipationMode,
      memory_scope: String(data.get("memory_scope")) as MemoryScope,
      version_label:
        String(data.get("version_label") ?? "Current").trim() || "Current",
      sticker_count: Number(data.get("sticker_count") ?? 0)
    };
    try {
      setWorking(true);
      setError(null);
      const saved = editingDeployment
        ? await deploymentApi.updateDeployment(editingDeployment.id, baseFields)
        : await deploymentApi.createDeployment({
            character_card_id: draftCharacterId,
            connection_id: draftConnectionId,
            ...baseFields,
            status: "paused"
          });

      if (connection?.platform === "discord") {
        const mode = String(data.get("identity_mode") ?? "webhook") as DeploymentIdentityMode;
        const displayName =
          String(data.get("identity_display_name") ?? "").trim() ||
          saved.character_display_name;
        const avatarUrl = String(data.get("identity_avatar_url") ?? "").trim();
        const addressAliases = String(data.get("identity_address_aliases") ?? "")
          .split(/\r?\n|,/u)
          .map((item) => item.trim())
          .filter(Boolean);
        await discordIdentityApi.update(saved.id, {
          mode,
          display_name: displayName,
          avatar_url: avatarUrl || null,
          address_aliases: addressAliases
        });
      }
      closeDeploymentForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function toggleDeployment(item: CharacterDeployment) {
    try {
      setWorking(true);
      await deploymentApi.updateDeploymentStatus(
        item.id,
        item.status === "active" ? "paused" : "active"
      );
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeDeployment(item: CharacterDeployment) {
    const confirmed = window.confirm(
      zh
        ? `移除 ${item.character_display_name} 在 ${destination(item, zh)} 的部署？`
        : `Remove ${item.character_display_name} from ${destination(item, zh)}?`
    );
    if (!confirmed) return;
    try {
      setWorking(true);
      await discordIdentityApi.delete(item.id).catch(() => undefined);
      await deploymentApi.deleteDeployment(item.id);
      if (editingDeployment?.id === item.id) closeDeploymentForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeConnection(item: PlatformConnection) {
    const confirmed = window.confirm(
      zh
        ? `删除连接“${item.display_name}”？其下的 Server 配置与部署也会被移除。`
        : `Delete “${item.display_name}”? Its server profiles and deployments will also be removed.`
    );
    if (!confirmed) return;
    try {
      setWorking(true);
      await deploymentApi.deleteConnection(item.id);
      if (editingConnection?.id === item.id) closeConnectionForm();
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  const canSaveDeployment =
    Boolean(selectedWorkspaceProfile && draftCharacterId && draftConnectionId) &&
    (formConnection?.platform !== "discord" ||
      Boolean(draftServerProfileId) ||
      Boolean(isLegacyExactDiscord));

  return (
    <main className="deployment-page">
      <section className="deployment-workspace-top">
        <header className="deployment-header">
          <div>
          <h1>{zh ? "部署工作区" : "DEPLOYMENT WORKSPACE"}</h1>
          <p>
            {zh
              ? "在 Discord Server 中管理角色、知识与互动。"
              : "Manage characters, knowledge, and interactions inside your Discord servers."}
          </p>
          </div>
          <div className="deployment-header-actions">
            {!demoMode && (
              <button className="paper-button" onClick={openConnectionManager}>
                {zh ? "平台连接" : "Connections"}
              </button>
            )}
            <button className="paper-button" onClick={onClose}>
              {zh ? "返回角色库" : "Back to library"}
            </button>
          </div>
        </header>

        <section className="server-passport-shell" aria-label={zh ? "Server 护照" : "Server passport"}>
          <DiscordServerProfilesPanel
            connections={connections}
            profiles={serverProfiles}
            catalog={serverCatalog}
            selectedProfileId={selectedServerProfileId}
            demoMode={demoMode}
            zh={zh}
            onSelectProfile={setSelectedServerProfileId}
            onChanged={load}
            onError={(message) => setError(message || null)}
            onOpenLogs={() => setEventLogOpen(true)}
          />
          {selectedWorkspaceProfile && (
            <div className="server-passport-meta">
              <span className="server-passport-label">SERVER PASSPORT</span>
              <dl>
                <div>
                  <dt>{zh ? "时区" : "Timezone"}</dt>
                  <dd>{serverTimezone ?? (loading ? (zh ? "读取中…" : "Loading…") : "—")}</dd>
                </div>
                <div>
                  <dt>{zh ? "连接状态" : "Connector"}</dt>
                  <dd>{selectedWorkspaceConnection ? statusLabel(selectedWorkspaceConnection.status) : "—"}</dd>
                </div>
                <div>
                  <dt>{zh ? "Discord 身份" : "Discord identity"}</dt>
                  <dd>
                    {selectedWorkspaceConnection
                      ? connectorDisplayName(selectedWorkspaceConnection) || selectedWorkspaceConnection.display_name
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>{zh ? "最近同步" : "Catalog synced"}</dt>
                  <dd>{selectedWorkspaceCatalog ? activityLabel(selectedWorkspaceCatalog.synced_at, zh) : "—"}</dd>
                </div>
              </dl>
            </div>
          )}
        </section>

        <aside className="deployment-workspace-quote" aria-label={zh ? "工作区说明" : "Workspace note"}>
          <p>
            {zh
              ? "让角色在同一个地方生活、互动并共同成长。"
              : "A place where characters live, interact, and grow together."}
          </p>
          <span aria-hidden="true">♡</span>
        </aside>
      </section>

      {error && (
        <p className="error-note deployment-error" role="alert">
          {error}
        </p>
      )}

      <section className="server-notebook-shell">
        <nav className="server-notebook-tabs" aria-label={zh ? "Server 手帐分页" : "Server notebook pages"}>
          <span className="server-notebook-caption">SERVER NOTEBOOK</span>
          <button
            type="button"
            className={serverNotebookTab === "characters" ? "is-active" : ""}
            aria-current={serverNotebookTab === "characters" ? "page" : undefined}
            onClick={() => setServerNotebookTab("characters")}
          >
            <span aria-hidden="true">♙</span>
            <strong>{zh ? "角色部署" : "Characters"}</strong>
            <small>{deploymentTotal}</small>
          </button>
          <button
            type="button"
            className={serverNotebookTab === "knowledge" ? "is-active" : ""}
            aria-current={serverNotebookTab === "knowledge" ? "page" : undefined}
            onClick={() => setServerNotebookTab("knowledge")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">▤</span>
            <strong>{zh ? "知识库" : "Knowledge"}</strong>
          </button>
          <button
            type="button"
            className={serverNotebookTab === "interactions" ? "is-active" : ""}
            aria-current={serverNotebookTab === "interactions" ? "page" : undefined}
            onClick={() => setServerNotebookTab("interactions")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">⌁</span>
            <strong>{zh ? "角色互动" : "Interactions"}</strong>
          </button>
          <button
            type="button"
            className={serverNotebookTab === "intelligence" ? "is-active" : ""}
            aria-current={serverNotebookTab === "intelligence" ? "page" : undefined}
            onClick={() => setServerNotebookTab("intelligence")}
            disabled={!selectedWorkspaceProfile}
          >
            <span aria-hidden="true">◉</span>
            <strong>{zh ? "对话智能" : "Intelligence"}</strong>
          </button>
          <small className="server-notebook-hint">
            {zh ? "每次只展开一页，减少纵向堆叠。" : "One server page at a time."}
          </small>
        </nav>

        <div className="server-notebook-content">
          {serverNotebookTab === "characters" && (
            <div className="server-characters-page">
              <div className="server-characters-main">
                <section className="deployment-summary-grid">
                <article className="paper-sheet deployment-summary-card">
                  <span>{zh ? "总数" : "Total"}</span>
                  <strong>{selectedWorkspaceProfile ? deploymentTotal : "—"}</strong>
                  <small>{zh ? "精确位置或 Server 范围" : "Exact or server-wide scopes"}</small>
                </article>
                <article className="paper-sheet deployment-summary-card">
                  <span>{zh ? "运行中" : "Active"}</span>
                  <strong>{selectedWorkspaceProfile ? deploymentCounts.active : "—"}</strong>
                  <small>{zh ? "Connector 正在读取的部署" : "Read by the connector"}</small>
                </article>
                <article className="paper-sheet deployment-summary-card">
                  <span>{zh ? "已暂停" : "Paused"}</span>
                  <strong>{selectedWorkspaceProfile ? deploymentCounts.paused : "—"}</strong>
                  <small>{zh ? "保留配置但不参与" : "Configured but not participating"}</small>
                </article>
                <article className="paper-sheet deployment-summary-card">
                  <span>{zh ? "需要处理" : "Needs attention"}</span>
                  <strong>{selectedWorkspaceProfile ? deploymentCounts.attention : "—"}</strong>
                  <small>{zh ? "离线或错误状态" : "Offline or error states"}</small>
                </article>
                <article className="paper-sheet deployment-summary-card">
                  <span>{zh ? "同步 Channel" : "Synced Channels"}</span>
                  <strong>{selectedWorkspaceProfile ? selectedWorkspaceCatalog?.channels.length ?? "—" : "—"}</strong>
                  <small>
                    {selectedWorkspaceProfile
                      ? selectedWorkspaceProfile.guild_name
                      : zh
                        ? "尚未选择 Server"
                        : "No Server selected"}
                  </small>
                </article>
                </section>

                <section className="deployment-layout deployment-files-layout">
                {connectionManagerOpen && !demoMode && (
                  <PaperDrawer
                    onClose={closeConnectionManager}
                    ariaLabel={zh ? "平台连接" : "Platform connections"}
                    className="connection-manager-drawer"
                  >
                  <aside className="deployment-sidebar">
                  <section className="paper-sheet connection-panel">
                    <div className="panel-heading-row">
                      <div>
                        <p className="tape-label">CONNECTIONS</p>
                        <h2>{zh ? "平台账户" : "Platform accounts"}</h2>
                      </div>
                      {!demoMode && !connectionOpen && (
                        <button className="paper-button" onClick={openNewConnection}>
                          {zh ? "+ 添加" : "+ Add"}
                        </button>
                      )}
                    </div>

                    {connectionOpen && !demoMode && (
                      <form
                        className="connection-form"
                        onSubmit={saveConnection}
                        key={editingConnection?.id ?? "new-connection"}
                      >
                        <div className="panel-heading-row">
                          <strong>
                            {editingConnection
                              ? zh
                                ? "编辑平台账户"
                                : "Edit platform account"
                              : zh
                                ? "添加平台账户"
                                : "Add platform account"}
                          </strong>
                          <button type="button" className="text-button" onClick={closeConnectionForm}>
                            {zh ? "取消" : "Cancel"}
                          </button>
                        </div>
                        <label>
                          {zh ? "平台" : "Platform"}
                          <select
                            value={connectionPlatform}
                            onChange={(event) =>
                              changeConnectionPlatform(event.currentTarget.value as PlatformId)
                            }
                            disabled={Boolean(editingConnection)}
                          >
                            <option value="discord">Discord</option>
                            <option value="whatsapp">WhatsApp</option>
                            <option value="telegram">Telegram</option>
                          </select>
                        </label>
                        <label>
                          {zh ? "账户显示名称" : "Account display name"}
                          <input
                            name="display_name"
                            required
                            defaultValue={editingConnection?.display_name ?? ""}
                            placeholder={zh ? "例如：主要 Discord Bot" : "e.g. Main Discord Bot"}
                          />
                        </label>
                        <label>
                          {zh ? "运行方式" : "Run mode"}
                          <select
                            value={connectionMode}
                            onChange={(event) =>
                              setConnectionMode(event.currentTarget.value as ConnectionMode)
                            }
                          >
                            <option value="managed">{zh ? "云端托管" : "Managed cloud"}</option>
                            <option value="local">{zh ? "本地 Connector" : "Local connector"}</option>
                          </select>
                        </label>
                        <label>
                          {zh ? "外部账号 ID（可选）" : "External account ID (optional)"}
                          <input
                            name="external_account_id"
                            defaultValue={editingConnection?.external_account_id ?? ""}
                          />
                        </label>
                        <p className="connection-note">
                          {editingConnection
                            ? zh
                              ? "平台类型建立后不能修改。管理标签不会被 Connector Heartbeat 覆盖。"
                              : "The platform is immutable after creation. Connector heartbeats do not overwrite the management label."
                            : zh
                              ? platformNotes[connectionPlatform].zh
                              : platformNotes[connectionPlatform].en}
                        </p>
                        <button className="ink-button" disabled={working}>
                          {working
                            ? zh
                              ? "保存中…"
                              : "Saving…"
                            : editingConnection
                              ? zh
                                ? "保存账户修改"
                                : "Save account changes"
                              : zh
                                ? "保存连接"
                                : "Save connection"}
                        </button>
                      </form>
                    )}

                    <div className="connection-list">
                      {connections.map((item) => {
                        const runtimeName = connectorDisplayName(item);
                        return (
                          <article className="connection-card" key={item.id}>
                            <div className={`platform-icon platform-${item.platform}`} aria-hidden="true">
                              {item.platform.slice(0, 1).toUpperCase()}
                            </div>
                            <div>
                              <strong>{item.display_name}</strong>
                              <span>
                                {platformLabels[item.platform]} · {item.connection_mode}
                              </span>
                              {runtimeName && runtimeName !== item.display_name && (
                                <small>{zh ? "Connector 身份" : "Connector identity"}: {runtimeName}</small>
                              )}
                              {item.external_account_id && <small>ID: {item.external_account_id}</small>}
                              {item.metadata.shared_connection === true && (
                                <small>
                                  {zh
                                    ? "由 Super Admin 管理；当前账号只使用已认领 Server"
                                    : "Managed by the Super Admin; this account only uses claimed Servers"}
                                </small>
                              )}
                            </div>
                            <span className={`deployment-status status-${item.status}`}>
                              {statusLabel(item.status)}
                            </span>
                            {!demoMode && item.metadata.shared_connection !== true && (
                              <div className="connection-card-actions">
                                <button
                                  className="text-button"
                                  onClick={() => openEditConnection(item)}
                                  disabled={working}
                                >
                                  {zh ? "编辑" : "Edit"}
                                </button>
                                <button
                                  className="text-button danger-text"
                                  onClick={() => void removeConnection(item)}
                                  disabled={working}
                                >
                                  {zh ? "删除" : "Delete"}
                                </button>
                              </div>
                            )}
                          </article>
                        );
                      })}
                      {!loading && connections.length === 0 && (
                        <div className="deployment-empty compact-empty">
                          <strong>{zh ? "还没有平台连接" : "No platform connections yet"}</strong>
                          <p>{zh ? "先添加平台连接，再建立部署。" : "Add a platform connection first."}</p>
                        </div>
                      )}
                    </div>
                  </section>
                </aside>
                  </PaperDrawer>
                )}

                <section className="deployment-main">
                  {deploymentOpen && !demoMode && (
                    <PaperDrawer
                      onClose={closeDeploymentForm}
                      ariaLabel={editingDeployment
                        ? zh
                          ? "编辑角色部署"
                          : "Edit character deployment"
                        : zh
                          ? "新建角色部署"
                          : "New character deployment"}
                      className="deployment-editor-drawer"
                    >
                    <section className="paper-sheet deployment-form-sheet">
                      <div className="panel-heading-row">
                        <div>
                          <p className="tape-label">
                            {editingDeployment ? "EDIT DEPLOYMENT" : "NEW DEPLOYMENT"}
                          </p>
                          <h2>
                            {editingDeployment
                              ? zh
                                ? "编辑现有部署"
                                : "Edit deployment"
                              : zh
                                ? "将角色部署到 Discord Server 或聊天位置"
                                : "Deploy a character to a Discord server or chat destination"}
                          </h2>
                        </div>
                        <button className="paper-button" onClick={closeDeploymentForm}>
                          {zh ? "关闭" : "Close"}
                        </button>
                      </div>
                      {selectedWorkspaceProfile && (
                        <div className="deployment-server-context">
                          <span>{zh ? "当前 Server" : "Current Server"}</span>
                          <strong>{selectedWorkspaceProfile.guild_name}</strong>
                          <small>{selectedWorkspaceProfile.name} · ID {selectedWorkspaceProfile.guild_id}</small>
                        </div>
                      )}
                      <p className="deployment-foundation-note">
                        {discordIdentityEnabled
                          ? zh
                            ? "选择 Server 配置后，角色默认进入该 Server 的全部可见 Channel。这里只需要再移除不适合该角色的位置。"
                            : "After selecting a server profile, the character covers every visible channel by default. Remove only destinations that do not fit this character."
                          : zh
                            ? "修改会保留当前部署状态。"
                            : "Edits preserve the current deployment status."}
                      </p>
                      <form
                        className="deployment-form"
                        onSubmit={saveDeployment}
                        key={editingDeployment?.id ?? "new-deployment"}
                      >
                        <label>
                          {zh ? "角色" : "Character"}
                          <select
                            value={draftCharacterId}
                            onChange={(event) => setDraftCharacterId(event.currentTarget.value)}
                            disabled={Boolean(editingDeployment)}
                            required
                          >
                            {cards.map((card) => (
                              <option value={card.id} key={card.id}>
                                {card.display_name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          {zh ? "平台连接" : "Platform connection"}
                          <select
                            value={draftConnectionId}
                            onChange={(event) => changeDeploymentConnection(event.currentTarget.value)}
                            disabled={Boolean(editingDeployment) || Boolean(selectedWorkspaceProfile)}
                            required
                          >
                            {connections.map((item) => (
                              <option value={item.id} key={item.id}>
                                {item.display_name} · {platformLabels[item.platform]}
                              </option>
                            ))}
                          </select>
                        </label>

                        {discordIdentityEnabled ? (
                          <>
                            <label className="deployment-form-wide">
                              {zh ? "Discord Server 配置" : "Discord server profile"}
                              <select
                                value={draftServerProfileId}
                                onChange={(event) => changeServerProfile(event.currentTarget.value)}
                                disabled={Boolean(selectedWorkspaceProfile)}
                                required={!isLegacyExactDiscord}
                              >
                                {isLegacyExactDiscord && (
                                  <option value="">
                                    {zh ? "旧版：固定 Channel / Thread" : "Legacy: exact channel / thread"}
                                  </option>
                                )}
                                {connectionProfiles.map((profile) => (
                                  <option value={profile.id} key={profile.id}>
                                    {profile.name} · {profile.guild_name}
                                  </option>
                                ))}
                              </select>
                              <small>
                                {connectionProfiles.length
                                  ? zh
                                    ? "Server ID 与 Channel 清单由 Connector 自动同步。"
                                    : "The connector supplies the server ID and channel inventory."
                                  : zh
                                    ? "请先在左侧建立 Discord Server 配置。"
                                    : "Create a Discord server profile in the left panel first."}
                              </small>
                            </label>

                            {selectedProfile && (
                              <div className="deployment-form-wide deployment-channel-picker">
                                <div className="deployment-form-divider">
                                  <strong>{zh ? "角色专属 Channel 排除" : "Character-specific channel exclusions"}</strong>
                                  <span>
                                    {zh
                                      ? `默认允许全部。Server 配置已全局排除 ${selectedProfile.excluded_channel_ids.length + selectedProfile.excluded_category_ids.length} 个位置。`
                                      : `Everything is allowed by default. The server profile already excludes ${selectedProfile.excluded_channel_ids.length + selectedProfile.excluded_category_ids.length} destinations globally.`}
                                  </span>
                                </div>
                                {deploymentChannelGroups.map((group) => {
                                  const categoryGloballyExcluded =
                                    Boolean(group.id) && globallyExcludedCategories.has(group.id);
                                  return (
                                    <fieldset key={group.id || "uncategorized"}>
                                      <legend>
                                        {group.id && (
                                          <input
                                            type="checkbox"
                                            checked={
                                              categoryGloballyExcluded || excludedCategories.has(group.id)
                                            }
                                            disabled={categoryGloballyExcluded}
                                            onChange={() =>
                                              toggleSet(
                                                excludedCategories,
                                                group.id,
                                                setExcludedCategories
                                              )
                                            }
                                          />
                                        )}
                                        {group.name}
                                        {categoryGloballyExcluded && (
                                          <small>{zh ? "（全局排除）" : " (globally excluded)"}</small>
                                        )}
                                      </legend>
                                      {group.channels.map((channel) => {
                                        const globallyExcluded =
                                          categoryGloballyExcluded ||
                                          globallyExcludedChannels.has(channel.id);
                                        return (
                                          <label key={channel.id} className="server-channel-option">
                                            <input
                                              type="checkbox"
                                              checked={globallyExcluded || excludedChannels.has(channel.id)}
                                              disabled={globallyExcluded}
                                              onChange={() =>
                                                toggleSet(
                                                  excludedChannels,
                                                  channel.id,
                                                  setExcludedChannels
                                                )
                                              }
                                            />
                                            <span>#{channel.name}</span>
                                            <small>
                                              {globallyExcluded
                                                ? zh
                                                  ? "全局排除"
                                                  : "globally excluded"
                                                : channel.type}
                                            </small>
                                          </label>
                                        );
                                      })}
                                    </fieldset>
                                  );
                                })}
                                {!selectedCatalog && (
                                  <p className="connection-note">
                                    {zh
                                      ? "Connector 暂时没有该 Server 的最新 Channel 清单。现有排除 ID 会保留，但需等待同步后才能从清单中选择。"
                                      : "The connector has not reported the latest channel inventory for this server. Existing exclusion IDs remain stored; wait for sync to select from the list."}
                                  </p>
                                )}
                              </div>
                            )}

                            {isLegacyExactDiscord && (
                              <>
                                <div className="deployment-form-wide deployment-form-divider">
                                  <strong>{zh ? "旧版精确位置" : "Legacy exact destination"}</strong>
                                  <span>
                                    {zh
                                      ? "保持原本行为，或在上方选择 Server 配置进行转换。"
                                      : "Keep the existing behavior or select a server profile above to convert it."}
                                  </span>
                                </div>
                                <label>
                                  {zh ? "Server 名称" : "Server name"}
                                  <input
                                    name="workspace_name"
                                    defaultValue={editingDeployment?.workspace_name ?? ""}
                                  />
                                </label>
                                <label>
                                  {zh ? "Server ID" : "Server ID"}
                                  <input
                                    name="workspace_id"
                                    defaultValue={editingDeployment?.workspace_id ?? ""}
                                  />
                                </label>
                                <label>
                                  {zh ? "Channel 名称" : "Channel name"}
                                  <input
                                    name="channel_name"
                                    required
                                    defaultValue={editingDeployment?.channel_name ?? ""}
                                  />
                                </label>
                                <label>
                                  {zh ? "Channel ID" : "Channel ID"}
                                  <input
                                    name="channel_id"
                                    required
                                    defaultValue={editingDeployment?.channel_id ?? ""}
                                  />
                                </label>
                                <label>
                                  {zh ? "Thread 名称（可选）" : "Thread name (optional)"}
                                  <input
                                    name="thread_name"
                                    defaultValue={editingDeployment?.thread_name ?? ""}
                                  />
                                </label>
                                <label>
                                  {zh ? "Thread ID（可选）" : "Thread ID (optional)"}
                                  <input
                                    name="thread_id"
                                    defaultValue={editingDeployment?.thread_id ?? ""}
                                  />
                                </label>
                              </>
                            )}
                          </>
                        ) : (
                          <>
                            <label>
                              {zh ? "Server / Workspace 名称" : "Server / workspace name"}
                              <input
                                name="workspace_name"
                                defaultValue={editingDeployment?.workspace_name ?? ""}
                              />
                            </label>
                            <label>
                              {zh ? "Server / Workspace ID" : "Server / workspace ID"}
                              <input
                                name="workspace_id"
                                defaultValue={editingDeployment?.workspace_id ?? ""}
                              />
                            </label>
                            <label>
                              {zh ? "Channel / Group 名称" : "Channel / group name"}
                              <input
                                name="channel_name"
                                required
                                defaultValue={editingDeployment?.channel_name ?? ""}
                              />
                            </label>
                            <label>
                              {zh ? "Channel / Group ID" : "Channel / group ID"}
                              <input
                                name="channel_id"
                                required
                                defaultValue={editingDeployment?.channel_id ?? ""}
                              />
                            </label>
                            <label>
                              {zh ? "Thread 名称（可选）" : "Thread name (optional)"}
                              <input
                                name="thread_name"
                                defaultValue={editingDeployment?.thread_name ?? ""}
                              />
                            </label>
                            <label>
                              {zh ? "Thread ID（可选）" : "Thread ID (optional)"}
                              <input
                                name="thread_id"
                                defaultValue={editingDeployment?.thread_id ?? ""}
                              />
                            </label>
                          </>
                        )}

                        <label>
                          {zh ? "参与模式" : "Participation mode"}
                          <select
                            name="participation_mode"
                            value={draftParticipationMode}
                            onChange={(event) =>
                              setDraftParticipationMode(
                                event.currentTarget.value as ParticipationMode
                              )
                            }
                          >
                            <option value="mention_only">Mention only</option>
                            <option value="reply_only">Reply only</option>
                            <option value="mention_and_reply">Mention + reply</option>
                            <option value="smart">Smart participation</option>
                          </select>
                          <small className="deployment-participation-help">
                            {participationHelp(draftParticipationMode, zh)}
                          </small>
                        </label>
                        <label>
                          {zh ? "记忆范围" : "Memory scope"}
                          <select
                            name="memory_scope"
                            defaultValue={editingDeployment?.memory_scope ?? "channel_isolated"}
                          >
                            <option value="channel_isolated">Channel isolated</option>
                            <option value="server_shared">Server shared</option>
                            <option value="custom">Custom</option>
                          </select>
                        </label>

                        {editingDeployment ? (
                          <DeploymentToolSelector
                            deploymentId={editingDeployment.id}
                            disabled={working}
                            zh={zh}
                          />
                        ) : (
                          <section className="deployment-form-wide deployment-tool-selector">
                            <div className="deployment-form-divider">
                              <strong>{zh ? "角色工具 / Tool Calling" : "Character tools / Tool Calling"}</strong>
                              <span>
                                {zh
                                  ? "先建立 Deployment，再从编辑页面为这个角色手动分配工具。工具属于 Deployment，不写进 Character Card。"
                                  : "Create the Deployment first, then edit it to assign tools manually. Tools belong to the Deployment, not the Character Card."}
                              </span>
                            </div>
                          </section>
                        )}

                        {discordIdentityEnabled && draftParticipationMode === "smart" && (
                          <div className="deployment-form-wide deployment-smart-participation">
                            <SmartParticipationStudio
                              cards={cards}
                              zh={zh}
                              fixedCharacterId={draftCharacterId}
                              embedded
                            />
                          </div>
                        )}

                        <label>
                          {zh ? "角色版本" : "Character version"}
                          <input
                            name="version_label"
                            defaultValue={editingDeployment?.version_label ?? "Current"}
                          />
                        </label>
                        <label>
                          {zh ? "已配置贴图数量" : "Configured stickers"}
                          <input
                            name="sticker_count"
                            type="number"
                            min="0"
                            max="500"
                            defaultValue={editingDeployment?.sticker_count ?? 0}
                          />
                        </label>

                        {discordIdentityEnabled && (
                          <>
                            <div className="deployment-form-wide deployment-form-divider">
                              <strong>{zh ? "Discord 消息身份" : "Discord message identity"}</strong>
                              <span>
                                {zh
                                  ? "Webhook 会在实际发送 Channel 中按需建立，并使用角色名称与头像。"
                                  : "The connector provisions the webhook in the actual channel on demand and uses the character name and avatar."}
                              </span>
                            </div>
                            <label>
                              {zh ? "发送方式" : "Delivery identity"}
                              <select name="identity_mode" defaultValue={formIdentity?.mode ?? "webhook"}>
                                <option value="webhook">
                                  {zh ? "角色 Webhook 身份" : "Character webhook identity"}
                                </option>
                                <option value="bot">{zh ? "共用 Bot 身份" : "Shared Bot identity"}</option>
                              </select>
                            </label>
                            <label>
                              {zh ? "显示名称" : "Display name"}
                              <input
                                name="identity_display_name"
                                maxLength={80}
                                defaultValue={
                                  formIdentity?.display_name ??
                                  cards.find((card) => card.id === draftCharacterId)?.display_name ??
                                  "Character"
                                }
                              />
                            </label>
                            <label className="deployment-form-wide">
                              {zh ? "角色称呼 Alias" : "Character address aliases"}
                              <input
                                name="identity_address_aliases"
                                defaultValue={(
                                  formIdentity?.address_aliases.length
                                    ? formIdentity.address_aliases
                                    : inferredAddressAliases(
                                        formIdentity?.display_name ?? "",
                                        cards.find((card) => card.id === draftCharacterId)?.display_name ?? ""
                                      )
                                ).join(", ")}
                                placeholder={zh ? "安, Ann" : "Ann, 安"}
                              />
                              <small>
                                {zh
                                  ? "用逗号分隔。路由会优先使用这些明确称呼，不再依赖显示名称格式。"
                                  : "Comma-separated explicit routing names, independent of display-name formatting."}
                              </small>
                            </label>
                            <label className="deployment-form-wide">
                              {zh ? "头像公开 URL（可选）" : "Public avatar URL (optional)"}
                              <input
                                name="identity_avatar_url"
                                type="url"
                                defaultValue={formIdentity?.avatar_url ?? ""}
                                placeholder="https://.../avatar.png"
                              />
                            </label>
                          </>
                        )}

                        <button
                          className="ink-button deployment-submit"
                          disabled={working || !canSaveDeployment}
                        >
                          {working
                            ? zh
                              ? "保存中…"
                              : "Saving…"
                            : editingDeployment
                              ? zh
                                ? "保存部署修改"
                                : "Save deployment changes"
                              : zh
                                ? "建立暂停状态的部署"
                                : "Create paused deployment"}
                        </button>
                      </form>
                    </section>
                    </PaperDrawer>
                  )}

                  <section className="paper-sheet deployment-list-sheet">
                    <div className="panel-heading-row deployment-list-heading">
                      <div>
                        <p className="tape-label">CHARACTER DEPLOYMENT FILES</p>
                        <h2>{zh ? "这个 Server 中的角色" : "CHARACTERS IN THIS SERVER"}</h2>
                        <p className="deployment-list-subtitle">
                          {zh
                            ? "每份档案都保留角色在当前 Server 的 Presence、参与、记忆与 Discord 身份。"
                            : "Each file records this Character's Presence, participation, memory, and Discord identity in the selected Server."}
                        </p>
                      </div>
                      <span>
                        {selectedWorkspaceProfile ? `${deployments.length} / ${deploymentTotal}` : "—"}
                      </span>
                      {!demoMode && (
                        <button
                          className="ink-button"
                          onClick={openNewDeployment}
                          disabled={!cards.length || !selectedWorkspaceProfile}
                        >
                          {zh ? "+ 新部署" : "+ New deployment"}
                        </button>
                      )}
                    </div>

                    <div className="deployment-filters">
                      <label>
                        {zh ? "角色" : "Character"}
                        <select
                          value={characterFilter}
                          onChange={(event) => setCharacterFilter(event.currentTarget.value)}
                        >
                          <option value="all">{zh ? "全部角色" : "All characters"}</option>
                          {cards.map((card) => (
                            <option value={card.id} key={card.id}>
                              {card.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {zh ? "状态" : "Status"}
                        <select
                          value={statusFilter}
                          onChange={(event) =>
                            setStatusFilter(event.currentTarget.value as "all" | DeploymentStatus)
                          }
                        >
                          <option value="all">{zh ? "全部状态" : "All statuses"}</option>
                          <option value="active">Active</option>
                          <option value="paused">Paused</option>
                          <option value="offline">Offline</option>
                          <option value="error">Error</option>
                          <option value="disconnected">Disconnected</option>
                        </select>
                      </label>
                    </div>

                    {loading ? (
                      <div className="deployment-empty">
                        <strong>{zh ? "正在读取部署…" : "Loading deployments…"}</strong>
                      </div>
                    ) : deployments.length === 0 ? (
                      <div className="deployment-empty">
                        <strong>
                          {!selectedWorkspaceProfile
                            ? zh
                              ? "先添加或选择一个 Discord Server"
                              : "Choose a Discord Server to open its Character files"
                            : deploymentTotal
                            ? zh
                              ? "没有符合筛选条件的部署"
                              : "No deployments match the filters"
                            : zh
                              ? "还没有角色部署"
                              : "No character deployments yet"}
                        </strong>
                        <p>
                          {!selectedWorkspaceProfile
                            ? zh
                              ? "Server 是部署、Interaction 与运行状态的权限范围。"
                              : "Server scope protects deployments, interactions, and runtime state."
                            : zh
                              ? "Discord 新部署会复用 Server 配置，并默认覆盖全部 Channel。"
                              : "New Discord deployments reuse a server profile and cover all channels by default."}
                        </p>
                      </div>
                    ) : (
                      <div className="deployment-file-grid" role="list">
                        {deployments.map((item) => {
                          const identity = identityMap.get(item.id) ?? defaultIdentity(item);
                          const card = cardMap.get(item.character_card_id);
                          const tools = deploymentTools[item.id];
                          const profile = item.server_profile_id
                            ? profileMap.get(item.server_profile_id)
                            : undefined;
                          const totalExclusions =
                            new Set([
                              ...(profile?.excluded_channel_ids ?? []),
                              ...item.excluded_channel_ids
                            ]).size +
                            new Set([
                              ...(profile?.excluded_category_ids ?? []),
                              ...item.excluded_category_ids
                            ]).size;
                          return (
                            <article
                              className={`deployment-file deployment-file-${item.status}`}
                              role="listitem"
                              key={item.id}
                            >
                              <span className="deployment-file-tab">DEPLOYMENT FILE</span>
                              <header className="deployment-file-header">
                                <div className={`deployment-file-portrait portrait-${card?.portrait_variant ?? "lavender"}`}>
                                  <CharacterPortrait
                                    cardId={item.character_card_id}
                                    alt={item.character_display_name}
                                  />
                                </div>
                                <div className="deployment-file-identity">
                                  <span>{item.version_label}</span>
                                  <h3>{item.character_display_name}</h3>
                                  <p>{card?.subtitle || (zh ? "角色部署档案" : "Character deployment file")}</p>
                                </div>
                                <span className={`deployment-status status-${item.status}`}>
                                  {statusLabel(item.status)}
                                </span>
                              </header>

                              <dl className="deployment-file-facts">
                                <div className="deployment-file-presence">
                                  <dt>{zh ? "Presence / Channel 范围" : "Presence / Channel scope"}</dt>
                                  <dd>{destination(item, zh)}</dd>
                                  {item.channel_scope_mode === "all_except" && (
                                    <small>
                                      {item.server_profile_name || profile?.name} ·{" "}
                                      {zh ? `共排除 ${totalExclusions} 个位置` : `${totalExclusions} total exclusions`}
                                    </small>
                                  )}
                                </div>
                                <div>
                                  <dt>{zh ? "参与方式" : "Participation"}</dt>
                                  <dd>{participationLabel(item.participation_mode, zh)}</dd>
                                </div>
                                <div>
                                  <dt>{zh ? "记忆范围" : "Memory"}</dt>
                                  <dd>{memoryLabel(item.memory_scope, zh)}</dd>
                                </div>
                                <div>
                                  <dt>{zh ? "Discord 身份" : "Discord identity"}</dt>
                                  <dd>{identity.mode === "webhook" ? "Webhook" : "Bot"} · {identity.display_name}</dd>
                                  <small>{statusLabel(identity.webhook_status)}</small>
                                </div>
                                <div>
                                  <dt>{zh ? "工具" : "Tools"}</dt>
                                  <dd>
                                    {tools === undefined
                                      ? "—"
                                      : zh
                                        ? `${tools.length} 个已启用`
                                        : `${tools.length} enabled`}
                                  </dd>
                                  {tools && tools.length > 0 && (
                                    <small title={tools.join(", ")}>{tools.slice(0, 2).join(" · ")}</small>
                                  )}
                                </div>
                              </dl>

                              {(item.last_error || identity.last_error) && (
                                <div className="deployment-file-error" role="status">
                                  {item.last_error || identity.last_error}
                                </div>
                              )}

                              <footer className="deployment-file-footer">
                                <div className="deployment-file-activity">
                                  <span>{zh ? "最近活动" : "Last activity"}</span>
                                  <strong>{activityLabel(item.last_message_at, zh)}</strong>
                                </div>
                                {!demoMode && (
                                  <div className="deployment-actions">
                                    <button
                                      className="ink-button"
                                      onClick={() => openEditDeployment(item)}
                                      disabled={working}
                                    >
                                      {zh ? "打开部署" : "Open Deployment"}
                                    </button>
                                    <button
                                      className="paper-button"
                                      onClick={() => void toggleDeployment(item)}
                                      disabled={
                                        working ||
                                        item.status === "offline" ||
                                        item.status === "disconnected"
                                      }
                                    >
                                      {item.status === "active"
                                        ? zh
                                          ? "暂停"
                                          : "Pause"
                                        : zh
                                          ? "启用"
                                          : "Activate"}
                                    </button>
                                    <details className="deployment-file-more">
                                      <summary>{zh ? "更多" : "More"}</summary>
                                      <button
                                        className="text-button danger-text"
                                        onClick={() => void removeDeployment(item)}
                                        disabled={working}
                                      >
                                        {zh ? "移除部署" : "Remove deployment"}
                                      </button>
                                    </details>
                                  </div>
                                )}
                              </footer>
                            </article>
                          );
                        })}
                      </div>
                    )}
                    <Pagination
                      page={deploymentPage}
                      pages={deploymentPages}
                      total={deploymentTotal}
                      disabled={loading || working}
                      onPage={(page) => void load(page)}
                    />
                  </section>
                </section>
              </section>
              </div>

              <aside className="server-characters-rail" aria-label={zh ? "Server 边栏" : "Server workspace notes"}>
                <section className="server-rail-note server-scope-note">
                  <span>{zh ? "SERVER 范围" : "SERVER SCOPE"}</span>
                  {selectedWorkspaceProfile ? (
                    <dl>
                      <div>
                        <dt>{zh ? "Server" : "Server"}</dt>
                        <dd>{selectedWorkspaceProfile.guild_name}</dd>
                      </div>
                      <div>
                        <dt>{zh ? "可见 Channel" : "Visible Channels"}</dt>
                        <dd>{selectedWorkspaceCatalog?.channels.length ?? "—"}</dd>
                      </div>
                      <div>
                        <dt>{zh ? "默认排除" : "Default Exclusions"}</dt>
                        <dd>
                          {selectedWorkspaceProfile.excluded_channel_ids.length +
                            selectedWorkspaceProfile.excluded_category_ids.length}
                        </dd>
                      </div>
                      <div>
                        <dt>{zh ? "时区" : "Timezone"}</dt>
                        <dd>{serverTimezone ?? "—"}</dd>
                      </div>
                    </dl>
                  ) : (
                    <p>
                      {zh
                        ? "添加或选择 Server 后，这里会显示它的真实范围。"
                        : "Add or choose a Server to see its authoritative scope."}
                    </p>
                  )}
                </section>

                <section className="server-rail-note server-quick-links">
                  <span>{zh ? "快捷入口" : "QUICK LINKS"}</span>
                  {!demoMode && (
                    <button type="button" onClick={openConnectionManager}>
                      {zh ? "平台连接" : "Platform Connections"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setEventLogOpen(true)}
                    disabled={!selectedWorkspaceProfile}
                  >
                    {zh ? "Server 日志" : "Server Log"}
                  </button>
                  {!demoMode && (
                    <button
                      type="button"
                      onClick={openNewDeployment}
                      disabled={!cards.length || !selectedWorkspaceProfile}
                    >
                      {zh ? "部署角色" : "Deploy Character"}
                    </button>
                  )}
                </section>

                <section className="server-rail-note server-health-note">
                  <span>{zh ? "运行检查" : "HEALTH CHECK"}</span>
                  <ul>
                    <li className={selectedWorkspaceProfile ? "is-good" : "needs-attention"}>
                      <span>{zh ? "Server 配置" : "Server Profile"}</span>
                      <strong>{selectedWorkspaceProfile ? "✓" : "—"}</strong>
                    </li>
                    <li className={selectedWorkspaceConnection?.status === "connected" ? "is-good" : "needs-attention"}>
                      <span>{zh ? "连接" : "Connection"}</span>
                      <strong>{selectedWorkspaceConnection ? statusLabel(selectedWorkspaceConnection.status) : "—"}</strong>
                    </li>
                    <li className={selectedWorkspaceCatalog ? "is-good" : "needs-attention"}>
                      <span>{zh ? "Channel Catalog" : "Channel Catalog"}</span>
                      <strong>{selectedWorkspaceCatalog ? "✓" : "—"}</strong>
                    </li>
                    <li className={serverTimezone ? "is-good" : "needs-attention"}>
                      <span>{zh ? "时区" : "Timezone"}</span>
                      <strong>{serverTimezone ? "✓" : "—"}</strong>
                    </li>
                  </ul>
                </section>
              </aside>
            </div>
          )}

          {serverNotebookTab === "knowledge" && (
            <KnowledgeBasePanel
              profile={selectedWorkspaceProfile}
              catalog={selectedWorkspaceCatalog}
              cards={cards}
              demoMode={demoMode}
              zh={zh}
            />
          )}

          {serverNotebookTab === "interactions" && selectedWorkspaceProfile && (
            <InteractionSessionsPanel
              demoMode={demoMode}
              zh={zh}
              serverProfile={selectedWorkspaceProfile}
              serverCatalog={selectedWorkspaceCatalog}
            />
          )}

          {serverNotebookTab === "intelligence" && selectedWorkspaceProfile && (
            <ConversationIntelligenceInspector
              cards={cards}
              profile={selectedWorkspaceProfile}
              catalog={selectedWorkspaceCatalog}
              zh={zh}
            />
          )}

          {serverNotebookTab !== "characters" && !selectedWorkspaceProfile && (
            <section className="server-notebook-empty paper-sheet">
              <strong>{zh ? "先选择一个 Discord Server" : "Choose a Discord Server first"}</strong>
              <p>{zh ? "Knowledge、Interaction 与 Intelligence 都属于当前 Server。" : "Knowledge, Interactions, and Intelligence are scoped to the selected Server."}</p>
            </section>
          )}
        </div>
      </section>

      {!demoMode && eventLogOpen && selectedWorkspaceProfile && (
        <PaperModal
          ariaLabel={
            zh
              ? `${selectedWorkspaceProfile.guild_name} Discord 日志`
              : `${selectedWorkspaceProfile.guild_name} Discord logs`
          }
          onClose={() => setEventLogOpen(false)}
          className="server-log-modal"
        >
          <DiscordEventLogPanel
            profiles={[selectedWorkspaceProfile]}
            selectedServerProfileId={selectedWorkspaceProfile.id}
            lockedServerProfileId={selectedWorkspaceProfile.id}
            embedded
            zh={zh}
          />
        </PaperModal>
      )}
    </main>
  );
}
