from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


for path in ["web/src/CharacterShelf.tsx", "web/src/PortalToolbox.tsx"]:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    text = text.replace(
        "/assets/brand/character-relay-wordmark.webp",
        "/assets/brand/character-relay-wordmark.svg",
    )
    text = text.replace(
        "/assets/brand/character-relay-mark.webp",
        "/assets/brand/character-relay-mark.svg",
    )
    file.write_text(text, encoding="utf-8")

replace_once(
    "web/src/PortalToolbox.tsx",
    '''              {!publicDemo && (
                <button type="button" onClick={() => run(onAdmin)}>
                  <span className="toolbox-sticker sticker-rose">ADMIN</span>''',
    '''              {user.role === "admin" && !publicDemo && (
                <button type="button" onClick={() => run(onAdmin)}>
                  <span className="toolbox-sticker sticker-rose">ADMIN</span>''',
)

replace_once(
    "web/src/AccountPanel.tsx",
    '''  onDeleted: () => void;
}''',
    '''  onDeleted: () => void;
  embedded?: boolean;
}''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''export function AccountPanel({ user, onClose, onLogout, onDeleted }: Props) {''',
    '''export function AccountPanel({
  user,
  onClose,
  onLogout,
  onDeleted,
  embedded = false
}: Props) {''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="account-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-title"
        onMouseDown={(event) => event.stopPropagation()}
      >''',
    '''  const content = (
      <section
        className={`account-sheet paper-sheet${embedded ? " account-sheet-embedded" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-title"
        onMouseDown={(event) => event.stopPropagation()}
      >''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''        <button className="close-button" onClick={onClose} aria-label={t.close}>
          ×
        </button>''',
    '''        {!embedded && (
          <button className="close-button" onClick={onClose} aria-label={t.close}>
            ×
          </button>
        )}''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''      </section>
    </div>
  );
}''',
    '''      </section>
  );
  if (embedded) return content;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      {content}
    </div>
  );
}''',
)

replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''export function ProviderTraceViewer({ onClose }: { onClose: () => void }) {''',
    '''export function ProviderTraceViewer({
  onClose,
  embedded = false
}: {
  onClose: () => void;
  embedded?: boolean;
}) {''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''    <main className="provider-trace-page">''',
    '''    <main className={`provider-trace-page${embedded ? " provider-trace-embedded" : ""}`}>''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''          <button type="button" className="ink-button" onClick={onClose}>
            {zh ? "返回 Portal" : "Back to Portal"}
          </button>''',
    '''          {!embedded && (
            <button type="button" className="ink-button" onClick={onClose}>
              {zh ? "返回 Portal" : "Back to Portal"}
            </button>
          )}''',
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    '''import { Pagination } from "./Pagination";''',
    '''import { PaperDrawer } from "./NotebookUI";
import { Pagination } from "./Pagination";''',
)
deployment_file = Path("web/src/DeploymentCenter.tsx")
text = deployment_file.read_text(encoding="utf-8")

connection_start = '''            {connectionOpen && !demoMode && (
              <form'''
connection_new = '''            {connectionOpen && !demoMode && (
              <PaperDrawer
                onClose={closeConnectionForm}
                ariaLabel={editingConnection
                  ? zh
                    ? "编辑平台账户"
                    : "Edit platform account"
                  : zh
                    ? "添加平台账户"
                    : "Add platform account"}
                className="connection-editor-drawer"
              >
              <form'''
if connection_start not in text:
    raise SystemExit("Connection drawer start anchor not found")
text = text.replace(connection_start, connection_new, 1)
connection_close_old = '''              </form>
            )}'''
connection_end = text.index(connection_close_old, text.index(connection_new))
text = (
    text[:connection_end]
    + '''              </form>
              </PaperDrawer>
            )}'''
    + text[connection_end + len(connection_close_old):]
)

deployment_start = '''          {deploymentOpen && !demoMode && (
            <section className="paper-sheet deployment-form-sheet">'''
deployment_new = '''          {deploymentOpen && !demoMode && (
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
            <section className="paper-sheet deployment-form-sheet">'''
if deployment_start not in text:
    raise SystemExit("Deployment drawer start anchor not found")
text = text.replace(deployment_start, deployment_new, 1)
list_marker = text.index('''          <section className="paper-sheet deployment-list-sheet">''')
deployment_close_old = '''            </section>
          )}'''
deployment_close = text.rfind(
    deployment_close_old,
    text.index(deployment_new),
    list_marker,
)
if deployment_close < 0:
    raise SystemExit("Deployment drawer close anchor not found")
text = (
    text[:deployment_close]
    + '''            </section>
            </PaperDrawer>
          )}'''
    + text[deployment_close + len(deployment_close_old):]
)
deployment_file.write_text(text, encoding="utf-8")

replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''import { ServerStickerDictionary } from "./ServerStickerDictionary";''',
    '''import { PaperDrawer } from "./NotebookUI";
import { ServerStickerDictionary } from "./ServerStickerDictionary";''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''      {drawerOpen && !demoMode && (
        <div className="server-drawer-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeDrawer();
        }}>
          <aside className="server-drawer" role="dialog" aria-modal="true">''',
    '''      {drawerOpen && !demoMode && (
        <PaperDrawer
          onClose={closeDrawer}
          ariaLabel={editing
            ? zh
              ? `编辑 ${editing.guild_name}`
              : `Edit ${editing.guild_name}`
            : zh
              ? "添加 Discord Server"
              : "Add Discord Server"}
          className="server-profile-drawer"
        >
          <div className="server-drawer">''',
)
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''          </aside>
        </div>
      )}''',
    '''          </div>
        </PaperDrawer>
      )}''',
)

replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''] as const;

const EVENT_LABELS''',
    '''] as const;

const SHOW_SERVER_CONNECTION_STATUS = false;

const EVENT_LABELS''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  useEffect(() => {
    setStatusLoading(true);
    void loadStatus();
    const timer = window.setInterval(() => void loadStatus(), 10_000);
    return () => window.clearInterval(timer);
  }, [loadStatus]);''',
    '''  useEffect(() => {
    if (!SHOW_SERVER_CONNECTION_STATUS) return;
    setStatusLoading(true);
    void loadStatus();
    const timer = window.setInterval(() => void loadStatus(), 10_000);
    return () => window.clearInterval(timer);
  }, [loadStatus]);''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''      <section className="discord-server-status-section">''',
    '''      {SHOW_SERVER_CONNECTION_STATUS && (
      <section className="discord-server-status-section">''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''      </section>

      <div className="panel-heading-row discord-event-log-heading">''',
    '''      </section>
      )}

      <div className="panel-heading-row discord-event-log-heading">''',
)

replace_once(
    "web/index.html",
    '''    <meta name="theme-color" content="#17131d" />''',
    '''    <meta name="theme-color" content="#f4ecdd" />
    <link rel="icon" type="image/svg+xml" href="/assets/brand/character-relay-mark.svg" />''',
)

css = Path("web/src/notebook-ui.css")
extra = r'''

.paper-drawer-panel .server-drawer {
  position: static !important;
  width: auto !important;
  max-width: none !important;
  min-height: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.server-profile-drawer .drawer-close-button {
  display: none !important;
}

.connection-editor-drawer .connection-form,
.deployment-editor-drawer .deployment-form-sheet {
  margin: 0 !important;
  border: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
}

.connection-editor-drawer .connection-form {
  padding: 4px 0 24px !important;
}

.deployment-editor-drawer .deployment-form-sheet {
  padding: 4px 0 28px !important;
}

.shelf-primary-actions {
  position: static !important;
}

.journal-header,
.shelf-intro,
.library-toolbar,
.card-grid,
.character-card,
.blank-card,
.portal-toolbox-modal,
.account-sheet,
.provider-trace-controls,
.provider-trace-list,
.provider-trace-detail,
.server-workspace-panel,
.connection-panel,
.deployment-summary-card,
.deployment-list-sheet,
.interaction-session-panel {
  background-image: none !important;
  backdrop-filter: none !important;
}

.ink-button,
.paper-button,
.enter-room,
.binding-tabs button,
.account-tabs button,
.server-drawer-tabs button {
  background-image: none !important;
  box-shadow: none;
}

.ink-button {
  background: #7861bd !important;
}

.paper-button,
.enter-room {
  background: #fffaf2 !important;
}
'''
current = css.read_text(encoding="utf-8")
if ".paper-drawer-panel .server-drawer" not in current:
    css.write_text(current + extra, encoding="utf-8")
