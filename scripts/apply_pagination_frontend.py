from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"Expected snippet not found in {path}: {old[:140]!r}")
    target.write_text(text.replace(old, new, 1))


Path("web/src/Pagination.tsx").write_text(
    dedent(
        '''
        import { useI18n } from "./i18n";

        interface Props {
          page: number;
          pages: number;
          total: number;
          onPage: (page: number) => void;
          disabled?: boolean;
        }

        export function Pagination({ page, pages, total, onPage, disabled = false }: Props) {
          const { language } = useI18n();
          const zh = language === "zh-CN";
          if (pages <= 1 && total <= 0) return null;
          return (
            <nav
              className="library-pagination"
              aria-label={zh ? "分页" : "Pagination"}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                flexWrap: "wrap",
                marginTop: 18
              }}
            >
              <button
                type="button"
                className="paper-button"
                disabled={disabled || page <= 1}
                onClick={() => onPage(Math.max(1, page - 1))}
              >
                {zh ? "上一页" : "Previous"}
              </button>
              <span>
                {zh ? `第 ${page} / ${pages} 页 · ${total} 条` : `Page ${page} / ${pages} · ${total} items`}
              </span>
              <button
                type="button"
                className="paper-button"
                disabled={disabled || page >= pages}
                onClick={() => onPage(Math.min(pages, page + 1))}
              >
                {zh ? "下一页" : "Next"}
              </button>
            </nav>
          );
        }
        '''
    ).lstrip()
)

# Workspace API and Matrix Portal.
replace_once(
    "web/src/workspaceApi.ts",
    '''export interface MatrixListPage {
  items: MatrixView[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface MatrixTaskCombination {''',
    '''export interface MatrixListPage {
  items: MatrixView[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface MatrixTaskListPage {
  items: MatrixTaskView[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface MatrixTaskCombination {''',
)
replace_once(
    "web/src/workspaceApi.ts",
    '  matrixTasks: (id: string) => request<MatrixTaskView[]>(`/api/matrices/${id}/tasks`),',
    '''  matrixTasks: (
    id: string,
    page = 1,
    pageSize = 50,
    status: MatrixTaskStatus | "all" = "all"
  ) => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize)
    });
    if (status !== "all") query.set("status", status);
    return request<MatrixTaskListPage>(
      `/api/matrices/${id}/tasks/page?${query.toString()}`
    );
  },''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    'import { LanguageSwitcher } from "./LanguageSwitcher";\n',
    'import { LanguageSwitcher } from "./LanguageSwitcher";\nimport { Pagination } from "./Pagination";\n',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''  type MatrixPreview,
  type MatrixTaskView,
  type MatrixView,''',
    '''  type MatrixListPage,
  type MatrixPreview,
  type MatrixTaskListPage,
  type MatrixTaskStatus,
  type MatrixTaskView,
  type MatrixView,''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''  const [matrices, setMatrices] = useState<MatrixView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    try {
      const [nextPacks, nextMatrices] = await Promise.all([
        workspaceApi.listPacks(),
        workspaceApi.listMatrices()
      ]);
      setPacks(nextPacks);
      setMatrices(nextMatrices.items);
      setSelectedId((current) => current ?? nextMatrices.items[0]?.id ?? null);
      setMessage(null);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : c.requestFailed);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!matrices.some((item) => ["queued", "running"].includes(item.status))) return;
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [matrices]);''',
    '''  const [matrices, setMatrices] = useState<MatrixView[]>([]);
  const [matrixPage, setMatrixPage] = useState(1);
  const [matrixPages, setMatrixPages] = useState(1);
  const [matrixTotal, setMatrixTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load(page = matrixPage) {
    try {
      const [nextPacks, nextMatrices] = await Promise.all([
        workspaceApi.listPacks(),
        workspaceApi.listMatrices(page)
      ]);
      setPacks(nextPacks);
      setMatrices(nextMatrices.items);
      setMatrixPage(nextMatrices.page);
      setMatrixPages(nextMatrices.pages);
      setMatrixTotal(nextMatrices.total);
      setSelectedId((current) =>
        current && nextMatrices.items.some((item) => item.id === current)
          ? current
          : nextMatrices.items[0]?.id ?? null
      );
      setMessage(null);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : c.requestFailed);
    }
  }

  useEffect(() => { void load(1); }, []);
  useEffect(() => {
    if (!matrices.some((item) => ["queued", "running"].includes(item.status))) return;
    const timer = window.setInterval(() => void load(matrixPage), 2000);
    return () => window.clearInterval(timer);
  }, [matrices, matrixPage]);''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''          onChanged={load}
          onMessage={setMessage}
          copy={c}''',
    '''          onChanged={() => load(matrixPage)}
          onMessage={setMessage}
          page={matrixPage}
          pages={matrixPages}
          total={matrixTotal}
          onPage={(page) => void load(page)}
          copy={c}''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''  onChanged,
  onMessage,
  copy: c
}: {
  matrices: MatrixView[];
  selected: MatrixView | null;
  onSelect: (id: string) => void;
  onChanged: () => Promise<void>;
  onMessage: (message: string | null) => void;
  copy: Copy;
}) {
  const [tasks, setTasks] = useState<MatrixTaskView[]>([]);
  useEffect(() => {
    if (!selected) { setTasks([]); return; }
    void workspaceApi.matrixTasks(selected.id).then(setTasks).catch(() => setTasks([]));
  }, [selected?.id, selected?.updated_at]);''',
    '''  onChanged,
  onMessage,
  page,
  pages,
  total,
  onPage,
  copy: c
}: {
  matrices: MatrixView[];
  selected: MatrixView | null;
  onSelect: (id: string) => void;
  onChanged: () => Promise<void>;
  onMessage: (message: string | null) => void;
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
  copy: Copy;
}) {
  const [taskPage, setTaskPage] = useState<MatrixTaskListPage | null>(null);
  const [taskPageNumber, setTaskPageNumber] = useState(1);
  const [taskStatus, setTaskStatus] = useState<MatrixTaskStatus | "all">("all");

  async function loadTasks(nextPage = taskPageNumber, nextStatus = taskStatus) {
    if (!selected) {
      setTaskPage(null);
      return;
    }
    try {
      const next = await workspaceApi.matrixTasks(
        selected.id,
        nextPage,
        50,
        nextStatus
      );
      setTaskPage(next);
      setTaskPageNumber(next.page);
    } catch {
      setTaskPage(null);
    }
  }

  useEffect(() => {
    setTaskPageNumber(1);
    void loadTasks(1, taskStatus);
  }, [selected?.id, selected?.updated_at, taskStatus]);''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''      {matrices.length === 0 ? <p>{c.noMatrices}</p> : matrices.map((matrix) => (
        <button key={matrix.id} className={selected?.id === matrix.id ? "selected" : ""} onClick={() => onSelect(matrix.id)}>
          <strong>{matrix.name}</strong><span>{matrix.status}</span><small>{matrix.completed_tasks}/{matrix.total_tasks}</small>
        </button>
      ))}
    </aside>''',
    '''      {matrices.length === 0 ? <p>{c.noMatrices}</p> : matrices.map((matrix) => (
        <button key={matrix.id} className={selected?.id === matrix.id ? "selected" : ""} onClick={() => onSelect(matrix.id)}>
          <strong>{matrix.name}</strong><span>{matrix.status}</span><small>{matrix.completed_tasks}/{matrix.total_tasks}</small>
        </button>
      ))}
      <Pagination page={page} pages={pages} total={total} onPage={onPage} />
    </aside>''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''        <div className="matrix-task-list">
          <h3>{c.tasks}</h3>
          {tasks.map((task) => <article className={`matrix-task paper-sheet status-${task.status}`} key={task.id}>''',
    '''        <div className="matrix-task-list">
          <div className="section-heading">
            <h3>{c.tasks}</h3>
            <select
              value={taskStatus}
              onChange={(event) =>
                setTaskStatus(event.currentTarget.value as MatrixTaskStatus | "all")
              }
            >
              <option value="all">All statuses</option>
              <option value="pending">{c.pending}</option>
              <option value="running">{c.running}</option>
              <option value="completed">{c.completed}</option>
              <option value="failed">{c.failed}</option>
              <option value="cancelled">{c.cancelled}</option>
            </select>
          </div>
          {(taskPage?.items ?? []).map((task) => <article className={`matrix-task paper-sheet status-${task.status}`} key={task.id}>''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''          </article>)}
        </div>
      </>}''',
    '''          </article>)}
          {taskPage && (
            <Pagination
              page={taskPage.page}
              pages={taskPage.pages}
              total={taskPage.total}
              onPage={(nextPage) => void loadTasks(nextPage, taskStatus)}
            />
          )}
        </div>
      </>}''',
)

# Provider Trace API and cursor navigation.
replace_once(
    "web/src/providerTraceApi.ts",
    '''export interface ProviderTraceView {
''',
    '''export interface ProviderTracePage {
  items: ProviderTraceView[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ProviderTraceView {
''',
)
replace_once(
    "web/src/providerTraceApi.ts",
    '''    traceId?: string;
  } = {}) => {
''',
    '''    traceId?: string;
    cursor?: string | null;
  } = {}) => {
''',
)
replace_once(
    "web/src/providerTraceApi.ts",
    '''    if (options.traceId?.trim()) query.set("trace_id", options.traceId.trim());
    return request<ProviderTraceView[]>(`/api/admin/provider-traces?${query.toString()}`);
''',
    '''    if (options.traceId?.trim()) query.set("trace_id", options.traceId.trim());
    if (options.cursor) query.set("cursor", options.cursor);
    return request<ProviderTracePage>(
      `/api/admin/provider-traces/page?${query.toString()}`
    );
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''  const [autoRefresh, setAutoRefresh] = useState(false);
  const [loading, setLoading] = useState(true);''',
    '''  const [autoRefresh, setAutoRefresh] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''  async function load() {
    try {
      setLoading(true);
      const next = await providerTraceApi.list({ limit: 200, status, model });
      setTraces(next);
      setSelectedId((current) =>
        current && next.some((item) => item.trace_id === current)
          ? current
          : next[0]?.trace_id ?? null
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [status]);''',
    '''  async function load(targetCursor: string | null = cursor) {
    try {
      setLoading(true);
      const next = await providerTraceApi.list({
        limit: 50,
        status,
        model,
        cursor: targetCursor
      });
      setTraces(next.items);
      setNextCursor(next.next_cursor);
      setSelectedId((current) =>
        current && next.items.some((item) => item.trace_id === current)
          ? current
          : next.items[0]?.trace_id ?? null
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function resetAndLoad() {
    setCursor(null);
    setCursorHistory([]);
    setPage(1);
    void load(null);
  }

  function showOlder() {
    if (!nextCursor) return;
    setCursorHistory((current) => [...current, cursor]);
    setCursor(nextCursor);
    setPage((current) => current + 1);
    void load(nextCursor);
  }

  function showNewer() {
    const previous = cursorHistory.at(-1);
    if (previous === undefined) return;
    setCursorHistory((current) => current.slice(0, -1));
    setCursor(previous);
    setPage((current) => Math.max(1, current - 1));
    void load(previous);
  }

  useEffect(() => {
    resetAndLoad();
  }, [status]);''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''    const timer = window.setInterval(() => void load(), 5000);
''',
    '''    const timer = window.setInterval(() => void load(cursor), 5000);
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''      setTraces([]);
      setSelectedId(null);
''',
    '''      setTraces([]);
      setSelectedId(null);
      setCursor(null);
      setCursorHistory([]);
      setNextCursor(null);
      setPage(1);
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''          <button type="button" className="paper-button" onClick={() => void load()}>
''',
    '''          <button type="button" className="paper-button" onClick={() => void load(cursor)}>
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''        <button type="button" className="paper-button" onClick={() => void load()}>
          {zh ? "套用筛选" : "Apply filters"}
        </button>''',
    '''        <button type="button" className="paper-button" onClick={resetAndLoad}>
          {zh ? "套用筛选" : "Apply filters"}
        </button>''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''          {traces.length} {zh ? "条" : "traces"}
''',
    '''          {zh ? `第 ${page} 页 · ${traces.length} 条` : `Page ${page} · ${traces.length} traces`}
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''            traces.map((trace) => (
''',
    '''            <>
              {traces.map((trace) => (
''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''            ))
          )}
        </aside>''',
    '''              ))}
              <nav className="library-pagination" style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
                <button type="button" className="paper-button" disabled={cursorHistory.length === 0 || loading} onClick={showNewer}>
                  {zh ? "较新" : "Newer"}
                </button>
                <span>{page}</span>
                <button type="button" className="paper-button" disabled={!nextCursor || loading} onClick={showOlder}>
                  {zh ? "较旧" : "Older"}
                </button>
              </nav>
            </>
          )}
        </aside>''',
)

# Audit API and Account Panel cursor navigation.
replace_once(
    "web/src/api.ts",
    '''export interface AuditEventView {
''',
    '''export interface AuditEventPage {
  items: AuditEventView[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface AuditEventView {
''',
)
replace_once(
    "web/src/api.ts",
    '''  listAuditEvents: () => request<AuditEventView[]>("/api/admin/audit"),
''',
    '''  listAuditEvents: () => request<AuditEventView[]>("/api/admin/audit"),
  listAuditEventsPage: (cursor: string | null = null, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<AuditEventPage>(`/api/admin/audit/page?${query.toString()}`);
  },
''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''  const [audit, setAudit] = useState<AuditEventView[]>([]);
  const [newCode, setNewCode] = useState<string | null>(null);''',
    '''  const [audit, setAudit] = useState<AuditEventView[]>([]);
  const [auditCursor, setAuditCursor] = useState<string | null>(null);
  const [auditCursorHistory, setAuditCursorHistory] = useState<Array<string | null>>([]);
  const [auditNextCursor, setAuditNextCursor] = useState<string | null>(null);
  const [auditPage, setAuditPage] = useState(1);
  const [newCode, setNewCode] = useState<string | null>(null);''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''      const [nextInvitations, nextUsers, nextAudit] = await Promise.all([
        api.listInvitations(),
        api.listAdminUsers(),
        api.listAuditEvents()
      ]);
      setInvitations(nextInvitations);
      setUsers(nextUsers);
      setAudit(nextAudit);''',
    '''      const [nextInvitations, nextUsers, nextAudit] = await Promise.all([
        api.listInvitations(),
        api.listAdminUsers(),
        api.listAuditEventsPage()
      ]);
      setInvitations(nextInvitations);
      setUsers(nextUsers);
      setAudit(nextAudit.items);
      setAuditCursor(null);
      setAuditCursorHistory([]);
      setAuditNextCursor(nextAudit.next_cursor);
      setAuditPage(1);''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''  async function run(action: () => Promise<void>) {
''',
    '''  async function loadAudit(cursor: string | null) {
    try {
      const next = await api.listAuditEventsPage(cursor);
      setAudit(next.items);
      setAuditNextCursor(next.next_cursor);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : t.loadError);
    }
  }

  function showOlderAudit() {
    if (!auditNextCursor) return;
    setAuditCursorHistory((current) => [...current, auditCursor]);
    setAuditCursor(auditNextCursor);
    setAuditPage((current) => current + 1);
    void loadAudit(auditNextCursor);
  }

  function showNewerAudit() {
    const previous = auditCursorHistory.at(-1);
    if (previous === undefined) return;
    setAuditCursorHistory((current) => current.slice(0, -1));
    setAuditCursor(previous);
    setAuditPage((current) => Math.max(1, current - 1));
    void loadAudit(previous);
  }

  async function run(action: () => Promise<void>) {
''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''                {audit.slice(0, 80).map((item) => (
''',
    '''                {audit.map((item) => (
''',
)
replace_once(
    "web/src/AccountPanel.tsx",
    '''              </div>
            </article>
          </div>
        )}''',
    '''              </div>
              <nav className="library-pagination" style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
                <button type="button" className="paper-button" disabled={auditCursorHistory.length === 0 || working} onClick={showNewerAudit}>
                  {language === "zh-CN" ? "较新" : "Newer"}
                </button>
                <span>{auditPage}</span>
                <button type="button" className="paper-button" disabled={!auditNextCursor || working} onClick={showOlderAudit}>
                  {language === "zh-CN" ? "较旧" : "Older"}
                </button>
              </nav>
            </article>
          </div>
        )}''',
)

# Deployment API and server-side list pagination.
replace_once(
    "web/src/deploymentApi.ts",
    '''export interface CharacterDeploymentCreate {
''',
    '''export interface CharacterDeploymentPage {
  items: CharacterDeployment[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
  active: number;
  paused: number;
  attention: number;
}

export interface CharacterDeploymentCreate {
''',
)
replace_once(
    "web/src/deploymentApi.ts",
    '''  listDeployments: (characterCardId?: string) =>
    request<CharacterDeployment[]>(
      characterCardId
        ? `/api/deployments?character_card_id=${encodeURIComponent(characterCardId)}`
        : "/api/deployments"
    ),''',
    '''  listDeployments: (characterCardId?: string) =>
    request<CharacterDeployment[]>(
      characterCardId
        ? `/api/deployments?character_card_id=${encodeURIComponent(characterCardId)}`
        : "/api/deployments"
    ),
  listDeploymentsPage: (options: {
    page?: number;
    pageSize?: number;
    characterCardId?: string;
    platform?: PlatformId | "all";
    status?: DeploymentStatus | "all";
  } = {}) => {
    const query = new URLSearchParams({
      page: String(options.page ?? 1),
      page_size: String(options.pageSize ?? 20)
    });
    if (options.characterCardId && options.characterCardId !== "all") {
      query.set("character_card_id", options.characterCardId);
    }
    if (options.platform && options.platform !== "all") {
      query.set("platform", options.platform);
    }
    if (options.status && options.status !== "all") {
      query.set("status", options.status);
    }
    return request<CharacterDeploymentPage>(
      `/api/deployments/page?${query.toString()}`
    );
  },''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\n',
    'import { DiscordServerProfilesPanel } from "./DiscordServerProfilesPanel";\nimport { Pagination } from "./Pagination";\n',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [identities, setIdentities] = useState<DeploymentMessageIdentity[]>([]);''',
    '''  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [deploymentPage, setDeploymentPage] = useState(1);
  const [deploymentPages, setDeploymentPages] = useState(1);
  const [deploymentTotal, setDeploymentTotal] = useState(0);
  const [deploymentCounts, setDeploymentCounts] = useState({
    active: 0,
    paused: 0,
    attention: 0
  });
  const [identities, setIdentities] = useState<DeploymentMessageIdentity[]>([]);''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''  async function load() {
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
        deploymentApi.listDeployments(),
        discordIdentityApi.list()
      ]);
      setConnections(nextConnections);
      setServerProfiles(nextProfiles);
      setServerCatalog(nextCatalog);
      setDeployments(nextDeployments);
      setIdentities(nextIdentities);''',
    '''  async function load(page = deploymentPage) {
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
          platform: platformFilter,
          status: statusFilter
        }),
        discordIdentityApi.list()
      ]);
      setConnections(nextConnections);
      setServerProfiles(nextProfiles);
      setServerCatalog(nextCatalog);
      setDeployments(nextDeployments.items);
      setDeploymentPage(nextDeployments.page);
      setDeploymentPages(nextDeployments.pages);
      setDeploymentTotal(nextDeployments.total);
      setDeploymentCounts({
        active: nextDeployments.active,
        paused: nextDeployments.paused,
        attention: nextDeployments.attention
      });
      setIdentities(nextIdentities);''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''  useEffect(() => {
    void load();
  }, []);
''',
    '''  useEffect(() => {
    void load(1);
  }, [characterFilter, platformFilter, statusFilter]);
''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''  const filtered = useMemo(
    () =>
      deployments.filter(
        (item) =>
          (platformFilter === "all" || item.platform === platformFilter) &&
          (statusFilter === "all" || item.status === statusFilter) &&
          (characterFilter === "all" || item.character_card_id === characterFilter)
      ),
    [characterFilter, deployments, platformFilter, statusFilter]
  );
  const counts = useMemo(
    () => ({
      active: deployments.filter((item) => item.status === "active").length,
      paused: deployments.filter((item) => item.status === "paused").length,
      attention: deployments.filter(
        (item) => item.status === "error" || item.status === "offline"
      ).length
    }),
    [deployments]
  );
''',
    '',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''          <strong>{counts.active}</strong>''',
    '''          <strong>{deploymentCounts.active}</strong>''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''          <strong>{counts.paused}</strong>''',
    '''          <strong>{deploymentCounts.paused}</strong>''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''          <strong>{counts.attention}</strong>''',
    '''          <strong>{deploymentCounts.attention}</strong>''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                {filtered.length} / {deployments.length}''',
    '''                {deployments.length} / {deploymentTotal}''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''            ) : filtered.length === 0 ? (''',
    '''            ) : deployments.length === 0 ? (''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                  {deployments.length
                    ? zh''',
    '''                  {deploymentTotal
                    ? zh''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                {filtered.map((item) => {''',
    '''                {deployments.map((item) => {''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''              </div>
            )}
          </section>''',
    '''              </div>
            )}
            <Pagination
              page={deploymentPage}
              pages={deploymentPages}
              total={deploymentTotal}
              disabled={loading || working}
              onPage={(page) => void load(page)}
            />
          </section>''',
)

Path(__file__).unlink()
