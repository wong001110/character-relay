import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard, JudgeMode, TestKind, TestLanguage, TesterMode } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ReportModal } from "./ReportModal";
import {
  workspaceApi,
  type ExperimentHistoryItem,
  type ExperimentHistoryPage,
  type ScenarioFields,
  type ScenarioView,
  type StorageDiagnostics,
  type TestPackFields,
  type TestPackView,
  type WorkspaceArchive
} from "./workspaceApi";
import "./workspace.css";

interface Props {
  cards: CharacterCard[];
  onClose: () => void;
}

type Tab = "scenarios" | "packs" | "experiments" | "storage";

const defaultScenario: ScenarioFields = {
  name: "",
  category: "identity_integrity",
  description: "",
  language: "en",
  messages: [""],
  expected_behavior: "",
  forbidden_phrases: [],
  required_phrases: [],
  severity: "medium",
  max_turns: 4,
  recommended_tester_mode: "benchmark",
  recommended_judge_mode: "hybrid"
};

const copy = {
  en: {
    title: "Workspace",
    subtitle: "Design tests, compose packs, and preserve reproducible experiment history.",
    close: "Character Library",
    scenarios: "Scenarios",
    packs: "Test Packs",
    experiments: "Experiments",
    storage: "Storage & Backup",
    newScenario: "New scenario",
    editScenario: "Edit scenario",
    scenarioName: "Scenario name",
    category: "Category",
    language: "Test language",
    description: "Description",
    messages: "Initial Tester messages",
    messagesHelp: "One message per line. Adaptive mode uses the first as its seed.",
    expected: "Expected behavior",
    forbidden: "Forbidden signals",
    required: "Required signals",
    listHelp: "One phrase per line.",
    severity: "Severity",
    maxTurns: "Maximum turns",
    testerMode: "Recommended Tester",
    judgeMode: "Recommended Judge",
    save: "Save",
    cancel: "Cancel",
    edit: "Edit",
    duplicate: "Duplicate",
    remove: "Delete",
    noScenarios: "No custom scenarios yet.",
    scenarioSaved: "Scenario saved.",
    newPack: "New pack",
    editPack: "Edit pack",
    packName: "Pack name",
    packDescription: "Description",
    included: "Included scenarios",
    noPacks: "No Test Packs yet.",
    version: "Version",
    enabled: "Enabled",
    disabled: "Disabled",
    moveUp: "Move up",
    moveDown: "Move down",
    packSaved: "Test Pack saved.",
    filters: "Filters",
    allCharacters: "All characters",
    allPacks: "All packs",
    allLanguages: "All languages",
    allTester: "All Tester modes",
    allJudge: "All Judge modes",
    refresh: "Refresh",
    score: "Score",
    verdict: "Verdict",
    report: "Report",
    baseline: "Baseline",
    setBaseline: "Set baseline",
    rerun: "Rerun",
    noExperiments: "No snapshotted experiments yet.",
    pass: "PASS",
    fail: "FAIL",
    review: "REVIEW",
    pending: "PENDING",
    storageTitle: "Storage diagnostics",
    adminToken: "Admin token",
    connect: "Load diagnostics",
    databasePath: "Database path",
    writable: "Writable",
    persistent: "Persistent path",
    counts: "Workspace counts",
    lastWrite: "Last write",
    createProbe: "Create persistence probe",
    probeHelp: "Create a marker, redeploy Railway, then check the same ID before deleting it.",
    checkProbe: "Check probe",
    deleteProbe: "Delete probe",
    export: "Export workspace",
    import: "Import workspace",
    merge: "Merge",
    replace: "Replace current workspace",
    importDone: "Workspace import completed.",
    noToken: "Enter the Admin token first.",
    yes: "Yes",
    no: "No",
    unknown: "Unknown",
    error: "The workspace request failed."
  },
  "zh-CN": {
    title: "实验工作区",
    subtitle: "设计测试、组合测试包，并保留可复现的实验历史。",
    close: "返回角色库",
    scenarios: "测试场景",
    packs: "测试包",
    experiments: "实验历史",
    storage: "存储与备份",
    newScenario: "新建场景",
    editScenario: "编辑场景",
    scenarioName: "场景名称",
    category: "分类",
    language: "测试语言",
    description: "说明",
    messages: "初始 Tester 消息",
    messagesHelp: "每行一条。Adaptive 模式使用第一条作为起始压力。",
    expected: "预期行为",
    forbidden: "禁止信号",
    required: "必要信号",
    listHelp: "每行一个短语。",
    severity: "严重度",
    maxTurns: "最大轮数",
    testerMode: "建议 Tester",
    judgeMode: "建议 Judge",
    save: "保存",
    cancel: "取消",
    edit: "编辑",
    duplicate: "复制",
    remove: "删除",
    noScenarios: "还没有自定义测试场景。",
    scenarioSaved: "场景已保存。",
    newPack: "新建测试包",
    editPack: "编辑测试包",
    packName: "测试包名称",
    packDescription: "说明",
    included: "包含的场景",
    noPacks: "还没有测试包。",
    version: "版本",
    enabled: "启用",
    disabled: "停用",
    moveUp: "上移",
    moveDown: "下移",
    packSaved: "测试包已保存。",
    filters: "筛选",
    allCharacters: "全部角色",
    allPacks: "全部测试包",
    allLanguages: "全部语言",
    allTester: "全部 Tester 模式",
    allJudge: "全部 Judge 模式",
    refresh: "刷新",
    score: "分数",
    verdict: "结论",
    report: "报告",
    baseline: "基准",
    setBaseline: "设为基准",
    rerun: "重新运行",
    noExperiments: "还没有带快照的实验记录。",
    pass: "通过",
    fail: "失败",
    review: "复核",
    pending: "进行中",
    storageTitle: "存储诊断",
    adminToken: "Admin Token",
    connect: "载入诊断",
    databasePath: "数据库路径",
    writable: "可写",
    persistent: "持久化路径",
    counts: "工作区数量",
    lastWrite: "最后写入",
    createProbe: "创建持久化探针",
    probeHelp: "创建标记后重新部署 Railway，再用同一个 ID 检查，最后删除。",
    checkProbe: "检查探针",
    deleteProbe: "删除探针",
    export: "导出工作区",
    import: "导入工作区",
    merge: "合并",
    replace: "替换当前工作区",
    importDone: "工作区导入完成。",
    noToken: "请先输入 Admin Token。",
    yes: "是",
    no: "否",
    unknown: "未知",
    error: "工作区请求失败。"
  }
} as const;

function lines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

export function WorkspaceHub({ cards, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [tab, setTab] = useState<Tab>("scenarios");
  const [scenarios, setScenarios] = useState<ScenarioView[]>([]);
  const [packs, setPacks] = useState<TestPackView[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  async function loadWorkspace() {
    try {
      const [nextScenarios, nextPacks] = await Promise.all([
        workspaceApi.listScenarios(),
        workspaceApi.listPacks()
      ]);
      setScenarios(nextScenarios);
      setPacks(nextPacks);
      setMessage(null);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : c.error);
    }
  }

  useEffect(() => { void loadWorkspace(); }, []);

  return (
    <main className="workspace-page">
      <header className="workspace-header">
        <div>
          <p className="kicker">Echo Masque</p>
          <h1>{c.title}</h1>
          <p>{c.subtitle}</p>
        </div>
        <div className="header-actions">
          <LanguageSwitcher />
          <button className="paper-button" onClick={onClose}>{c.close}</button>
        </div>
      </header>

      <nav className="workspace-tabs paper-sheet">
        {(["scenarios", "packs", "experiments", "storage"] as Tab[]).map((item) => (
          <button
            key={item}
            className={tab === item ? "selected" : ""}
            onClick={() => setTab(item)}
          >
            {c[item]}
          </button>
        ))}
      </nav>

      {message && <p className="error-note">{message}</p>}
      {tab === "scenarios" && (
        <ScenarioPanel
          copy={c}
          scenarios={scenarios}
          onChanged={loadWorkspace}
          onMessage={setMessage}
        />
      )}
      {tab === "packs" && (
        <PackPanel
          copy={c}
          scenarios={scenarios}
          packs={packs}
          onChanged={loadWorkspace}
          onMessage={setMessage}
        />
      )}
      {tab === "experiments" && (
        <ExperimentPanel copy={c} cards={cards} packs={packs} />
      )}
      {tab === "storage" && <StoragePanel copy={c} />}
    </main>
  );
}

type Copy = typeof copy.en | typeof copy["zh-CN"];

function ScenarioPanel({
  copy: c,
  scenarios,
  onChanged,
  onMessage
}: {
  copy: Copy;
  scenarios: ScenarioView[];
  onChanged: () => Promise<void>;
  onMessage: (message: string | null) => void;
}) {
  const [editing, setEditing] = useState<ScenarioView | null>(null);
  const [draft, setDraft] = useState<ScenarioFields | null>(null);

  function open(item?: ScenarioView) {
    setEditing(item ?? null);
    setDraft(item ? { ...item } : { ...defaultScenario, messages: [""] });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    try {
      if (editing) await workspaceApi.updateScenario(editing.id, draft);
      else await workspaceApi.createScenario(draft);
      setDraft(null);
      setEditing(null);
      onMessage(c.scenarioSaved);
      await onChanged();
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : c.error);
    }
  }

  return (
    <section className="workspace-section">
      <div className="section-heading">
        <div><p className="tape-label">{c.scenarios}</p><h2>{c.scenarios}</h2></div>
        <button className="ink-button" onClick={() => open()}>{c.newScenario}</button>
      </div>
      {draft && (
        <form className="workspace-form paper-sheet" onSubmit={submit}>
          <h3>{editing ? c.editScenario : c.newScenario}</h3>
          <label>{c.scenarioName}<input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })} required /></label>
          <label>{c.category}<select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.currentTarget.value as TestKind })}>
            <option value="identity_integrity">Identity integrity</option>
            <option value="false_memory">False memory</option>
            <option value="prompt_injection">Prompt injection</option>
            <option value="long_conversation_drift">Long drift</option>
          </select></label>
          <label>{c.language}<select value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.currentTarget.value as TestLanguage })}>
            <option value="en">English</option><option value="zh-CN">简体中文</option>
          </select></label>
          <label className="wide">{c.description}<textarea rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.currentTarget.value })} /></label>
          <label className="wide">{c.messages}<textarea rows={5} value={draft.messages.join("\n")} onChange={(e) => setDraft({ ...draft, messages: e.currentTarget.value.split("\n") })} required /><small>{c.messagesHelp}</small></label>
          <label className="wide">{c.expected}<textarea rows={4} value={draft.expected_behavior} onChange={(e) => setDraft({ ...draft, expected_behavior: e.currentTarget.value })} required /></label>
          <label>{c.forbidden}<textarea rows={4} value={draft.forbidden_phrases.join("\n")} onChange={(e) => setDraft({ ...draft, forbidden_phrases: lines(e.currentTarget.value) })} /><small>{c.listHelp}</small></label>
          <label>{c.required}<textarea rows={4} value={draft.required_phrases.join("\n")} onChange={(e) => setDraft({ ...draft, required_phrases: lines(e.currentTarget.value) })} /><small>{c.listHelp}</small></label>
          <label>{c.severity}<select value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.currentTarget.value as ScenarioFields["severity"] })}>
            <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
          </select></label>
          <label>{c.maxTurns}<input type="number" min="1" max="12" value={draft.max_turns} onChange={(e) => setDraft({ ...draft, max_turns: Number(e.currentTarget.value) })} /></label>
          <label>{c.testerMode}<select value={draft.recommended_tester_mode} onChange={(e) => setDraft({ ...draft, recommended_tester_mode: e.currentTarget.value as TesterMode })}><option value="benchmark">Benchmark</option><option value="adaptive">Adaptive</option></select></label>
          <label>{c.judgeMode}<select value={draft.recommended_judge_mode} onChange={(e) => setDraft({ ...draft, recommended_judge_mode: e.currentTarget.value as JudgeMode })}><option value="rules">Rules</option><option value="semantic">Semantic</option><option value="hybrid">Hybrid</option></select></label>
          <div className="form-actions wide"><button type="button" className="paper-button" onClick={() => setDraft(null)}>{c.cancel}</button><button className="ink-button">{c.save}</button></div>
        </form>
      )}
      {scenarios.length === 0 ? <div className="empty-library paper-sheet"><p>{c.noScenarios}</p></div> : (
        <div className="scenario-grid">
          {scenarios.map((item) => (
            <article className="scenario-card paper-sheet" key={item.id}>
              <div className="scenario-meta"><span>{item.language}</span><span>{item.category}</span><span>{item.severity}</span></div>
              <h3>{item.name}</h3><p>{item.description || item.expected_behavior}</p>
              <small>{item.messages.length} messages · {item.max_turns} turns</small>
              <div className="card-actions"><button className="paper-button" onClick={() => open(item)}>{c.edit}</button><button className="paper-button" onClick={() => void workspaceApi.duplicateScenario(item.id).then(onChanged)}>{c.duplicate}</button><button className="paper-button danger" onClick={() => void workspaceApi.deleteScenario(item.id).then(onChanged)}>{c.remove}</button></div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function PackPanel({ copy: c, scenarios, packs, onChanged, onMessage }: { copy: Copy; scenarios: ScenarioView[]; packs: TestPackView[]; onChanged: () => Promise<void>; onMessage: (message: string | null) => void }) {
  const [editing, setEditing] = useState<TestPackView | null>(null);
  const [draft, setDraft] = useState<TestPackFields | null>(null);
  function open(pack?: TestPackView) {
    setEditing(pack ?? null);
    setDraft(pack ? { name: pack.name, description: pack.description, items: [...pack.items].sort((a, b) => a.position - b.position).map((item) => ({ scenario_id: item.scenario.id, enabled: item.enabled })) } : { name: "", description: "", items: [] });
  }
  function toggle(id: string) {
    if (!draft) return;
    const existing = draft.items.find((item) => item.scenario_id === id);
    setDraft({ ...draft, items: existing ? draft.items.filter((item) => item.scenario_id !== id) : [...draft.items, { scenario_id: id, enabled: true }] });
  }
  function move(index: number, delta: number) {
    if (!draft) return;
    const next = [...draft.items]; const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setDraft({ ...draft, items: next });
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!draft) return;
    try { if (editing) await workspaceApi.updatePack(editing.id, draft); else await workspaceApi.createPack(draft); setDraft(null); setEditing(null); onMessage(c.packSaved); await onChanged(); }
    catch (reason) { onMessage(reason instanceof Error ? reason.message : c.error); }
  }
  const selected = useMemo(() => draft?.items.map((item) => scenarios.find((scenario) => scenario.id === item.scenario_id)).filter(Boolean) as ScenarioView[] ?? [], [draft, scenarios]);
  return <section className="workspace-section">
    <div className="section-heading"><div><p className="tape-label">{c.packs}</p><h2>{c.packs}</h2></div><button className="ink-button" onClick={() => open()}>{c.newPack}</button></div>
    {draft && <form className="workspace-form paper-sheet" onSubmit={submit}><h3>{editing ? c.editPack : c.newPack}</h3><label>{c.packName}<input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })} required /></label><label className="wide">{c.packDescription}<textarea value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.currentTarget.value })} /></label><fieldset className="wide"><legend>{c.included}</legend><div className="scenario-picker">{scenarios.map((item) => <label key={item.id}><input type="checkbox" checked={draft.items.some((selectedItem) => selectedItem.scenario_id === item.id)} onChange={() => toggle(item.id)} /><span>{item.name}</span><small>{item.language}</small></label>)}</div></fieldset><div className="pack-order wide">{selected.map((item, index) => <div key={item.id}><span>{index + 1}. {item.name}</span><button type="button" onClick={() => move(index, -1)}>{c.moveUp}</button><button type="button" onClick={() => move(index, 1)}>{c.moveDown}</button><button type="button" onClick={() => setDraft({ ...draft, items: draft.items.map((entry) => entry.scenario_id === item.id ? { ...entry, enabled: !entry.enabled } : entry) })}>{draft.items.find((entry) => entry.scenario_id === item.id)?.enabled ? c.enabled : c.disabled}</button></div>)}</div><div className="form-actions wide"><button type="button" className="paper-button" onClick={() => setDraft(null)}>{c.cancel}</button><button className="ink-button">{c.save}</button></div></form>}
    {packs.length === 0 ? <div className="empty-library paper-sheet"><p>{c.noPacks}</p></div> : <div className="pack-grid">{packs.map((pack) => <article className="pack-card paper-sheet" key={pack.id}><span>{c.version} {pack.version}</span><h3>{pack.name}</h3><p>{pack.description}</p><ul>{pack.items.slice(0, 6).map((item) => <li key={item.scenario.id}>{item.enabled ? "●" : "○"} {item.scenario.name} · {item.scenario.language}</li>)}</ul><div className="card-actions"><button className="paper-button" onClick={() => open(pack)}>{c.edit}</button><button className="paper-button" onClick={() => void workspaceApi.duplicatePack(pack.id).then(onChanged)}>{c.duplicate}</button><button className="paper-button danger" onClick={() => void workspaceApi.deletePack(pack.id).then(onChanged)}>{c.remove}</button></div></article>)}</div>}
  </section>;
}

function ExperimentPanel({ copy: c, cards, packs }: { copy: Copy; cards: CharacterCard[]; packs: TestPackView[] }) {
  const [history, setHistory] = useState<ExperimentHistoryPage | null>(null);
  const [character, setCharacter] = useState(""); const [pack, setPack] = useState(""); const [language, setLanguage] = useState(""); const [tester, setTester] = useState(""); const [judge, setJudge] = useState("");
  const [report, setReport] = useState<string | null>(null);
  async function load(page = 1) { const params = new URLSearchParams({ page: String(page), page_size: "20" }); if (character) params.set("character_card_id", character); if (pack) params.set("test_pack_id", pack); if (language) params.set("language", language); if (tester) params.set("tester_mode", tester); if (judge) params.set("judge_mode", judge); setHistory(await workspaceApi.history(params)); }
  useEffect(() => { void load(); }, []);
  function verdict(item: ExperimentHistoryItem) { if (item.review_required) return c.review; if (item.passed === true) return c.pass; if (item.passed === false) return c.fail; return c.pending; }
  return <section className="workspace-section"><div className="section-heading"><div><p className="tape-label">{c.experiments}</p><h2>{c.experiments}</h2></div><button className="paper-button" onClick={() => void load()}>{c.refresh}</button></div><div className="history-filters paper-sheet"><select value={character} onChange={(e) => setCharacter(e.currentTarget.value)}><option value="">{c.allCharacters}</option>{cards.map((item) => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select><select value={pack} onChange={(e) => setPack(e.currentTarget.value)}><option value="">{c.allPacks}</option>{packs.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select value={language} onChange={(e) => setLanguage(e.currentTarget.value)}><option value="">{c.allLanguages}</option><option value="en">English</option><option value="zh-CN">简体中文</option></select><select value={tester} onChange={(e) => setTester(e.currentTarget.value)}><option value="">{c.allTester}</option><option value="benchmark">Benchmark</option><option value="adaptive">Adaptive</option></select><select value={judge} onChange={(e) => setJudge(e.currentTarget.value)}><option value="">{c.allJudge}</option><option value="rules">Rules</option><option value="semantic">Semantic</option><option value="hybrid">Hybrid</option></select><button className="ink-button" onClick={() => void load()}>{c.filters}</button></div>{!history || history.items.length === 0 ? <div className="empty-library paper-sheet"><p>{c.noExperiments}</p></div> : <div className="history-list">{history.items.map((item) => <article className="history-row paper-sheet" key={item.run_id}><div><strong>{item.character_name}</strong><span>{item.test_pack_name ?? "Built-in suite"}</span></div><div><span>{item.test_language}</span><span>{item.tester_mode} · {item.judge_mode}</span></div><div><strong>{item.score === null ? "—" : item.score.toFixed(1)}</strong><span>{verdict(item)}</span></div><div className="history-actions"><button onClick={() => setReport(item.run_id)}>{c.report}</button><button onClick={() => void workspaceApi.setBaseline(item.run_id, !item.is_baseline).then(() => load())}>{item.is_baseline ? c.baseline : c.setBaseline}</button><button onClick={() => void workspaceApi.rerun(item.run_id).then(() => load())}>{c.rerun}</button><button className="danger" onClick={() => void workspaceApi.deleteExperiment(item.run_id).then(() => load())}>{c.remove}</button></div></article>)}</div>}{history && history.pages > 1 && <nav className="library-pagination"><button disabled={history.page === 1} onClick={() => void load(history.page - 1)}>←</button><span>{history.page} / {history.pages}</span><button disabled={history.page === history.pages} onClick={() => void load(history.page + 1)}>→</button></nav>}{report && <ReportModal runId={report} format="markdown" onClose={() => setReport(null)} />}</section>;
}

function StoragePanel({ copy: c }: { copy: Copy }) {
  const [token, setToken] = useState(() => window.sessionStorage.getItem("echo-masque-admin-token") ?? ""); const [diagnostics, setDiagnostics] = useState<StorageDiagnostics | null>(null); const [probe, setProbe] = useState<{ id: string; marker: string } | null>(null); const [message, setMessage] = useState<string | null>(null); const [importMode, setImportMode] = useState<"merge" | "replace">("merge");
  async function load() { if (!token) { setMessage(c.noToken); return; } try { window.sessionStorage.setItem("echo-masque-admin-token", token); setDiagnostics(await workspaceApi.storage(token)); setMessage(null); } catch (reason) { setMessage(reason instanceof Error ? reason.message : c.error); } }
  async function exportArchive() { const archive = await workspaceApi.exportWorkspace(token); const url = URL.createObjectURL(new Blob([JSON.stringify(archive, null, 2)], { type: "application/json" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `echo-masque-workspace-${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); URL.revokeObjectURL(url); }
  async function importArchive(file: File) { const archive = JSON.parse(await file.text()) as WorkspaceArchive; await workspaceApi.importWorkspace(token, archive, importMode); setMessage(c.importDone); await load(); }
  return <section className="workspace-section"><div className="section-heading"><div><p className="tape-label rose">{c.storage}</p><h2>{c.storageTitle}</h2></div></div><div className="storage-connect paper-sheet"><label>{c.adminToken}<input type="password" value={token} onChange={(e) => setToken(e.currentTarget.value)} /></label><button className="ink-button" onClick={() => void load()}>{c.connect}</button></div>{message && <p className="error-note">{message}</p>}{diagnostics && <div className="diagnostic-grid"><article className={`diagnostic-card paper-sheet ${diagnostics.warning ? "warning" : ""}`}><span>{c.databasePath}</span><strong>{diagnostics.database_path ?? diagnostics.database_url_redacted}</strong><p>{diagnostics.warning}</p></article><article className="diagnostic-card paper-sheet"><span>{c.writable}</span><strong>{diagnostics.writable ? c.yes : c.no}</strong><span>{c.persistent}</span><strong>{diagnostics.persistent_path_configured ? c.yes : c.no}</strong></article><article className="diagnostic-card paper-sheet"><span>{c.counts}</span><strong>{diagnostics.character_count} cards · {diagnostics.scenario_count} scenarios · {diagnostics.pack_count} packs · {diagnostics.run_count} runs</strong><span>{c.lastWrite}</span><strong>{diagnostics.last_write_at ?? c.unknown}</strong></article></div>}<div className="storage-tools"><article className="paper-sheet"><h3>{c.createProbe}</h3><p>{c.probeHelp}</p>{probe ? <><code>{probe.id}</code><div className="card-actions"><button onClick={() => void workspaceApi.getProbe(token, probe.id).then((value) => setMessage(`${c.checkProbe}: ${value.marker}`))}>{c.checkProbe}</button><button onClick={() => void workspaceApi.deleteProbe(token, probe.id).then(() => setProbe(null))}>{c.deleteProbe}</button></div></> : <button className="ink-button" onClick={() => void workspaceApi.createProbe(token, `probe-${Date.now()}`).then((value) => setProbe(value))}>{c.createProbe}</button>}</article><article className="paper-sheet"><h3>{c.export}</h3><button className="paper-button" onClick={() => void exportArchive()}>{c.export}</button><h3>{c.import}</h3><select value={importMode} onChange={(e) => setImportMode(e.currentTarget.value as "merge" | "replace")}><option value="merge">{c.merge}</option><option value="replace">{c.replace}</option></select><label className="file-button">{c.import}<input type="file" accept="application/json" onChange={(e) => { const file = e.currentTarget.files?.[0]; if (file) void importArchive(file); }} /></label></article></div></section>;
}
