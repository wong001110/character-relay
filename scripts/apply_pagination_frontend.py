from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"Expected snippet not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1))


# Matrix creation always returns to the newest page, and Analytics can browse pages.
replace_once(
    "web/src/MatrixWorkspace.tsx",
    "  type MatrixListPage,\n",
    "",
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    "  type MatrixTaskView,\n",
    "",
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''            await load();
            setTab("queue");''',
    '''            await load(1);
            setTab("queue");''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''        <MatrixAnalyticsPanel
          matrices={matrices}
          selected={selected}
          onSelect={setSelectedId}
          copy={c}
        />''',
    '''        <MatrixAnalyticsPanel
          matrices={matrices}
          selected={selected}
          onSelect={setSelectedId}
          page={matrixPage}
          pages={matrixPages}
          total={matrixTotal}
          onPage={(page) => void load(page)}
          copy={c}
        />''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''function MatrixAnalyticsPanel({ matrices, selected, onSelect, copy: c }: { matrices: MatrixView[]; selected: MatrixView | null; onSelect: (id: string) => void; copy: Copy }) {''',
    '''function MatrixAnalyticsPanel({
  matrices,
  selected,
  onSelect,
  page,
  pages,
  total,
  onPage,
  copy: c
}: {
  matrices: MatrixView[];
  selected: MatrixView | null;
  onSelect: (id: string) => void;
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
  copy: Copy;
}) {''',
)
replace_once(
    "web/src/MatrixWorkspace.tsx",
    '''    </div>
    {!analytics || analytics.completed_runs === 0 ?''',
    '''    </div>
    <Pagination page={page} pages={pages} total={total} onPage={onPage} />
    {!analytics || analytics.completed_runs === 0 ?''',
)

# Provider Trace keeps an applied model filter separate from the input and refreshes the active cursor.
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''  const [model, setModel] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);''',
    '''  const [model, setModel] = useState("");
  const [appliedModel, setAppliedModel] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''  async function load(targetCursor: string | null = cursor) {
    try {
      setLoading(true);
      const next = await providerTraceApi.list({
        limit: 50,
        status,
        model,
        cursor: targetCursor
      });''',
    '''  async function load(
    targetCursor: string | null = cursor,
    targetModel = appliedModel
  ) {
    try {
      setLoading(true);
      const next = await providerTraceApi.list({
        limit: 50,
        status,
        model: targetModel,
        cursor: targetCursor
      });''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''  function resetAndLoad() {
    setCursor(null);
    setCursorHistory([]);
    setPage(1);
    void load(null);
  }''',
    '''  function resetAndLoad(targetModel = appliedModel) {
    setCursor(null);
    setCursorHistory([]);
    setPage(1);
    void load(null, targetModel);
  }

  function applyFilters() {
    const nextModel = model.trim();
    setAppliedModel(nextModel);
    resetAndLoad(nextModel);
  }''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''    const timer = window.setInterval(() => void load(cursor), 5000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, status, model]);''',
    '''    const timer = window.setInterval(
      () => void load(cursor, appliedModel),
      5000
    );
    return () => window.clearInterval(timer);
  }, [autoRefresh, status, appliedModel, cursor]);''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''              if (event.key === "Enter") void load();''',
    '''              if (event.key === "Enter") applyFilters();''',
)
replace_once(
    "web/src/ProviderTraceViewer.tsx",
    '''        <button type="button" className="paper-button" onClick={resetAndLoad}>''',
    '''        <button type="button" className="paper-button" onClick={applyFilters}>''',
)

Path(__file__).unlink()
