from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Character shelf labels and the remaining stale SVG reference.
path = Path("web/src/CharacterShelf.tsx")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "/assets/brand/character-relay-mark.svg",
    "/assets/brand/character-relay-mark.png",
)
text = text.replace(
    '{zh ? "进入 Echo Masque" : "Open Echo Masque"}',
    '{zh ? "测试角色" : "Test Character"}',
)
path.write_text(text, encoding="utf-8")


# Server Workspace receives a server-scoped log action and clearer summary metrics.
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}''',
    '''  onChanged: () => Promise<void>;
  onError: (message: string) => void;
  onOpenLogs: () => void;
}''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''  onSelectProfile,
  onChanged,
  onError
}: Props) {''',
    '''  onSelectProfile,
  onChanged,
  onError,
  onOpenLogs
}: Props) {''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''  const selectedConnection = connections.find(
    (item) => item.id === selectedProfile?.connection_id
  );''',
    '''  const selectedConnection = connections.find(
    (item) => item.id === selectedProfile?.connection_id
  );
  const selectedServerCatalog = selectedProfile
    ? catalog.find(
        (item) =>
          item.connection_id === selectedProfile.connection_id &&
          item.guild_id === selectedProfile.guild_id
      )
    : undefined;''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''            <h2>{zh ? "先选择要管理的 Discord Server" : "Choose the Discord Server to manage"}</h2>''',
    '''            <h2>
              {selectedProfile
                ? zh
                  ? `${selectedProfile.guild_name} 工作区`
                  : `${selectedProfile.guild_name} workspace`
                : zh
                  ? "选择要管理的 Discord Server"
                  : "Choose the Discord Server to manage"}
            </h2>''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''              {selectedProfile && (
                <button className="paper-button" onClick={() => openEdit(selectedProfile)}>
                  {zh ? "编辑 Server" : "Edit Server"}
                </button>
              )}''',
    '''              {selectedProfile && (
                <>
                  <button
                    className="paper-button server-log-launcher"
                    type="button"
                    onClick={onOpenLogs}
                  >
                    {zh ? "查看 Server 日志" : "View Server logs"}
                  </button>
                  <button className="paper-button" onClick={() => openEdit(selectedProfile)}>
                    {zh ? "编辑 Server" : "Edit Server"}
                  </button>
                </>
              )}''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''                <div className="server-workspace-stat">
                  <strong>
                    {selectedProfile.excluded_channel_ids.length +
                      selectedProfile.excluded_category_ids.length}
                  </strong>
                  <span>{zh ? "排除位置" : "exclusions"}</span>
                </div>''',
    '''                <div className="server-workspace-stats">
                  <div className="server-workspace-stat">
                    <strong>{selectedServerCatalog?.channels.length ?? 0}</strong>
                    <span>{zh ? "可见 Channel" : "visible channels"}</span>
                  </div>
                  <div className="server-workspace-stat">
                    <strong>
                      {selectedProfile.excluded_channel_ids.length +
                        selectedProfile.excluded_category_ids.length}
                    </strong>
                    <span>{zh ? "排除位置" : "exclusions"}</span>
                  </div>
                </div>''',
)


# Deployment Center opens server logs in a dedicated fixed-height paper modal.
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''import { PaperDrawer } from "./NotebookUI";''',
    '''import { PaperDrawer, PaperModal } from "./NotebookUI";''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''  const [deploymentOpen, setDeploymentOpen] = useState(Boolean(initialCharacterId));
  const [editingDeployment, setEditingDeployment] = useState<CharacterDeployment | null>(null);''',
    '''  const [deploymentOpen, setDeploymentOpen] = useState(Boolean(initialCharacterId));
  const [eventLogOpen, setEventLogOpen] = useState(false);
  const [editingDeployment, setEditingDeployment] = useState<CharacterDeployment | null>(null);''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''        onChanged={load}
        onError={(message) => setError(message || null)}
      />''',
    '''        onChanged={load}
        onError={(message) => setError(message || null)}
        onOpenLogs={() => setEventLogOpen(true)}
      />''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''      {!demoMode && (
        <DiscordEventLogPanel
          profiles={serverProfiles}
          selectedServerProfileId={selectedServerProfileId}
          zh={zh}
        />
      )}''',
    '''      {!demoMode && eventLogOpen && selectedWorkspaceProfile && (
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
      )}''',
)


# Event Log supports a locked Server scope and embedded fixed-height presentation.
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''interface Props {
  profiles: DiscordServerProfile[];
  selectedServerProfileId: string;
  zh: boolean;
}''',
    '''interface Props {
  profiles: DiscordServerProfile[];
  selectedServerProfileId: string;
  lockedServerProfileId?: string;
  embedded?: boolean;
  zh: boolean;
}''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''export function DiscordEventLogPanel({
  profiles,
  selectedServerProfileId,
  zh
}: Props) {
  const [serverProfileId, setServerProfileId] = useState(selectedServerProfileId || "all");''',
    '''export function DiscordEventLogPanel({
  profiles,
  selectedServerProfileId,
  lockedServerProfileId = "",
  embedded = false,
  zh
}: Props) {
  const [serverProfileId, setServerProfileId] = useState(
    lockedServerProfileId || selectedServerProfileId || "all"
  );''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  useEffect(() => {
    if (selectedServerProfileId) setServerProfileId(selectedServerProfileId);
  }, [selectedServerProfileId]);''',
    '''  useEffect(() => {
    const nextProfileId = lockedServerProfileId || selectedServerProfileId;
    if (nextProfileId) {
      setServerProfileId(nextProfileId);
      setPage(1);
    }
  }, [lockedServerProfileId, selectedServerProfileId]);''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  const serverStatuses = useMemo(() => {
    const statuses = buildDiscordServerStatuses(profiles, connections, catalog);''',
    '''  const activeProfile = useMemo(
    () => profiles.find((item) => item.id === serverProfileId) ?? null,
    [profiles, serverProfileId]
  );

  const serverStatuses = useMemo(() => {
    const statuses = buildDiscordServerStatuses(profiles, connections, catalog);''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''    <section className="paper-sheet discord-event-log-panel">''',
    '''    <section
      className={`paper-sheet discord-event-log-panel${embedded ? " is-embedded" : ""}`}
    >''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''          <h2>{zh ? "Discord 触发与路由日志" : "Discord trigger and routing logs"}</h2>''',
    '''          <h2>
            {activeProfile
              ? zh
                ? `${activeProfile.guild_name} · Server 日志`
                : `${activeProfile.guild_name} · Server logs`
              : zh
                ? "Discord 触发与路由日志"
                : "Discord trigger and routing logs"}
          </h2>''',
)
server_filter = '''        <label>
          {zh ? "Server" : "Server"}
          <select
            value={serverProfileId}
            onChange={(event) => changeFilter(setServerProfileId, event.currentTarget.value)}
          >
            <option value="all">{zh ? "全部 Server" : "All servers"}</option>
            {profiles.map((profile) => (
              <option value={profile.id} key={profile.id}>
                {profile.guild_name} · {profile.name}
              </option>
            ))}
          </select>
        </label>'''
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    server_filter,
    '''        {!lockedServerProfileId && (
          <label>
            {zh ? "Server" : "Server"}
            <select
              value={serverProfileId}
              onChange={(event) => changeFilter(setServerProfileId, event.currentTarget.value)}
            >
              <option value="all">{zh ? "全部 Server" : "All servers"}</option>
              {profiles.map((profile) => (
                <option value={profile.id} key={profile.id}>
                  {profile.guild_name} · {profile.name}
                </option>
              ))}
            </select>
          </label>
        )}''',
)


# Append a small override layer after the existing notebook styles.
css_path = Path("web/src/notebook-ui.css")
css = css_path.read_text(encoding="utf-8")
marker = "/* Server workspace and shelf UX refinements */"
if marker not in css:
    css += r'''

/* Server workspace and shelf UX refinements */
html,
body,
#root {
  min-height: 100%;
  background: #f4ecdd !important;
  background-image: none !important;
}

.notebook-shell {
  width: 100% !important;
  max-width: none !important;
  padding-inline: clamp(20px, 4vw, 64px) !important;
}

.shelf-intro h2 {
  max-width: 760px;
  font-size: clamp(1.35rem, 2vw, 2rem) !important;
  line-height: 1.18;
}

.card-actions {
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
}

.card-actions .paper-button,
.card-actions .enter-room {
  min-height: 46px;
  padding: 9px 12px !important;
  border-radius: 14px !important;
  font-size: 0.84rem;
  line-height: 1.15;
}

.card-actions .enter-room {
  grid-column: 1 / -1;
  background: #7861bd !important;
  color: #fffaf2 !important;
  border: 1px solid #6c56ae !important;
}

.card-actions .enter-room:hover {
  background: #6c56ae !important;
}

.character-editor-drawer {
  padding-bottom: 0 !important;
}

.character-editor-drawer .notebook-form-paper {
  min-height: calc(100vh - 66px);
  padding-bottom: 0;
}

.character-editor-drawer .notebook-form-actions {
  bottom: 0;
  margin-top: auto;
  padding: 14px 0 max(14px, env(safe-area-inset-bottom));
  box-shadow: 0 -10px 20px rgba(68, 53, 79, 0.08);
}

.portal-toolbox-fab img {
  object-fit: contain !important;
  object-position: center !important;
  border-radius: 0 !important;
  padding: 2px;
}

.server-workspace-panel {
  max-width: 1440px;
  margin-inline: auto;
  padding: 24px;
}

.server-workspace-heading {
  display: grid !important;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start !important;
}

.server-workspace-heading h2 {
  font-size: clamp(1.45rem, 2.4vw, 2.25rem);
}

.server-workspace-selector-row {
  display: grid !important;
  grid-template-columns: minmax(260px, 0.65fr) minmax(0, 1.35fr);
  align-items: stretch !important;
}

.server-workspace-selector-row > label {
  align-content: center;
  min-width: 0 !important;
  padding: 16px;
  border: 1px dashed rgba(112, 86, 158, 0.22);
  border-radius: 14px;
  background: #fffaf2;
}

.server-workspace-current-card {
  display: grid !important;
  grid-template-columns: auto minmax(0, 1fr) auto;
  min-width: 0 !important;
  background: #fffaf2 !important;
  background-image: none !important;
}

.server-workspace-stats {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-left: auto;
}

.server-workspace-stat {
  min-width: 82px;
  margin-left: 0 !important;
}

.server-log-launcher {
  border-color: rgba(120, 97, 189, 0.38) !important;
  color: #5f4b97 !important;
}

.server-log-modal {
  display: flex;
  flex-direction: column;
  width: min(1120px, 96vw) !important;
  height: min(820px, 92vh);
  overflow: hidden !important;
}

.server-log-modal .paper-modal-topline {
  flex: 0 0 auto;
}

.discord-event-log-panel.is-embedded {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.discord-event-log-panel.is-embedded .discord-event-log-heading,
.discord-event-log-panel.is-embedded .discord-event-log-filters,
.discord-event-log-panel.is-embedded > .pagination {
  flex: 0 0 auto;
}

.discord-event-log-list {
  max-height: 480px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.discord-event-log-panel.is-embedded .discord-event-log-list {
  flex: 1;
  min-height: 220px;
  max-height: none;
  padding-right: 6px;
}

@media (max-width: 760px) {
  .server-workspace-heading,
  .server-workspace-selector-row,
  .server-workspace-current-card {
    grid-template-columns: 1fr !important;
  }

  .server-workspace-actions,
  .server-workspace-stats {
    justify-content: flex-start;
    margin-left: 0;
  }

  .server-workspace-stat {
    text-align: left;
  }

  .server-log-modal {
    width: 100% !important;
    height: 97vh;
  }
}
'''
    css_path.write_text(css, encoding="utf-8")
