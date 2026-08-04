import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard, JudgeMode, TestLanguage, TesterMode } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { Pagination } from "./Pagination";
import {
  workspaceApi,
  type MatrixAnalytics,
  type MatrixComparison,
  type MatrixDefinition,
  type MatrixFields,
  type MatrixListPage,
  type MatrixPreview,
  type MatrixTaskListPage,
  type MatrixTaskStatus,
  type MatrixTaskView,
  type MatrixView,
  type PromptVersionDiff,
  type PromptVersionView,
  type TestPackView
} from "./workspaceApi";
import "./matrix.css";

interface Props {
  cards: CharacterCard[];
  onClose: () => void;
}

type MatrixTab = "builder" | "queue" | "analytics" | "prompts";

const copy = {
  en: {
    title: "Matrix Lab",
    subtitle: "Run controlled batches across prompts, models, temperatures, languages, and judges.",
    close: "Character Library",
    builder: "Builder",
    queue: "Queue",
    analytics: "Analytics",
    prompts: "Prompt Versions",
    newMatrix: "New Matrix",
    matrixName: "Matrix name",
    description: "Description",
    subjects: "Character variants",
    packs: "Test Packs",
    models: "Model overrides",
    modelHelp: "One model ID per line. Leave empty to keep each card's current model.",
    temperatures: "Temperatures",
    temperatureHelp: "Comma-separated values from 0 to 2. Leave empty to keep current values.",
    languages: "Test languages",
    testerModes: "Tester modes",
    judgeModes: "Judge modes",
    repeats: "Repeat count",
    concurrency: "Concurrency",
    attempts: "Maximum attempts",
    preview: "Preview combinations",
    saveDraft: "Save draft",
    launch: "Launch confirmed Matrix",
    taskCount: "Planned tasks",
    limit: "Server limit",
    runtimeCost: "Adaptive and Semantic combinations consume provider calls.",
    noCards: "Create at least one Character Card first.",
    noPacks: "Create at least one Test Pack first.",
    noMatrices: "No Experiment Matrices yet.",
    refresh: "Refresh",
    selectMatrix: "Select a Matrix to inspect it.",
    pending: "Pending",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    pause: "Pause",
    resume: "Resume",
    cancel: "Cancel remaining",
    retry: "Retry failed",
    baseline: "Baseline",
    setBaseline: "Set baseline",
    remove: "Delete",
    tasks: "Tasks",
    run: "Run",
    attemptsLabel: "Attempts",
    error: "Error",
    score: "Mean score",
    passRate: "Pass rate",
    reviewRate: "Review rate",
    failureRate: "Failure rate",
    deviation: "Std. deviation",
    tokens: "Tokens",
    latency: "Latency",
    exports: "Exports",
    compare: "Regression comparison",
    compareWith: "Compare candidate",
    classification: "Classification",
    incompatible: "Incompatible dimensions",
    variants: "Variant breakdown",
    noAnalytics: "Launch and complete at least one task to populate analytics.",
    promptCard: "Prompt + Model card",
    version: "Version",
    active: "Active",
    production: "Production",
    restore: "Restore",
    markProduction: "Mark production",
    unmarkProduction: "Clear production",
    compareVersions: "Compare versions",
    changedFields: "Changed fields",
    promptBefore: "Earlier prompt",
    promptAfter: "Later prompt",
    noPromptVersions: "This card has no Prompt + Model versions.",
    currentConfig: "Current",
    saved: "Matrix draft saved.",
    launched: "Matrix launched.",
    confirmMismatch: "Preview the Matrix again before launch.",
    selectRequired: "Select at least one card, Test Pack, language, Tester, and Judge.",
    requestFailed: "Matrix request failed."
  },
  "zh-CN": {
    title: "矩阵实验室",
    subtitle: "批量对比提示词、模型、Temperature、语言与 Judge 配置。",
    close: "返回角色库",
    builder: "构建器",
    queue: "任务队列",
    analytics: "统计分析",
    prompts: "Prompt 版本",
    newMatrix: "新建矩阵",
    matrixName: "矩阵名称",
    description: "说明",
    subjects: "角色与 Prompt 版本",
    packs: "测试包",
    models: "模型覆盖",
    modelHelp: "每行一个模型 ID。留空则使用角色卡当前模型。",
    temperatures: "Temperature",
    temperatureHelp: "用逗号分隔 0 到 2 的数值。留空则使用当前值。",
    languages: "测试语言",
    testerModes: "Tester 模式",
    judgeModes: "Judge 模式",
    repeats: "重复次数",
    concurrency: "并发数",
    attempts: "最大尝试次数",
    preview: "预览组合数量",
    saveDraft: "保存草稿",
    launch: "确认并启动矩阵",
    taskCount: "计划任务数",
    limit: "服务器上限",
    runtimeCost: "Adaptive 与 Semantic 组合会消耗 Provider 调用。",
    noCards: "请先创建至少一张角色卡。",
    noPacks: "请先创建至少一个测试包。",
    noMatrices: "还没有实验矩阵。",
    refresh: "刷新",
    selectMatrix: "选择一个矩阵查看详情。",
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    pause: "暂停",
    resume: "继续",
    cancel: "取消剩余任务",
    retry: "重试失败任务",
    baseline: "基准",
    setBaseline: "设为基准",
    remove: "删除",
    tasks: "任务",
    run: "Run",
    attemptsLabel: "尝试次数",
    error: "错误",
    score: "平均分",
    passRate: "通过率",
    reviewRate: "复核率",
    failureRate: "失败率",
    deviation: "标准差",
    tokens: "Token",
    latency: "延迟",
    exports: "导出",
    compare: "回归比较",
    compareWith: "比较候选矩阵",
    classification: "判断",
    incompatible: "不兼容维度",
    variants: "配置分组",
    noAnalytics: "完成至少一个任务后才会产生统计数据。",
    promptCard: "Prompt + Model 角色卡",
    version: "版本",
    active: "当前启用",
    production: "Production",
    restore: "恢复",
    markProduction: "设为 Production",
    unmarkProduction: "取消 Production",
    compareVersions: "比较版本",
    changedFields: "变化字段",
    promptBefore: "旧 Prompt",
    promptAfter: "新 Prompt",
    noPromptVersions: "这张角色卡没有 Prompt + Model 版本。",
    currentConfig: "当前配置",
    saved: "矩阵草稿已保存。",
    launched: "矩阵已启动。",
    confirmMismatch: "请重新预览矩阵后再启动。",
    selectRequired: "至少选择一张角色卡、测试包、语言、Tester 和 Judge。",
    requestFailed: "矩阵请求失败。"
  }
} as const;

function initialDefinition(): MatrixDefinition {
  return {
    subjects: [],
    model_overrides: [],
    temperatures: [],
    test_pack_ids: [],
    test_languages: ["en"],
    tester_modes: ["benchmark"],
    judge_modes: ["rules"],
    repeat_count: 1,
    concurrency: 1,
    max_attempts: 2
  };
}

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

export function MatrixWorkspace({ cards, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [tab, setTab] = useState<MatrixTab>("builder");
  const [packs, setPacks] = useState<TestPackView[]>([]);
  const [matrices, setMatrices] = useState<MatrixView[]>([]);
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
  }, [matrices, matrixPage]);

  const selected = matrices.find((item) => item.id === selectedId) ?? null;

  return (
    <main className="matrix-page">
      <header className="matrix-header">
        <div>
          <p className="kicker">Echo Masque / Phase 14</p>
          <h1>{c.title}</h1>
          <p>{c.subtitle}</p>
        </div>
        <div className="header-actions">
          <LanguageSwitcher />
          <button className="paper-button" onClick={onClose}>{c.close}</button>
        </div>
      </header>

      <nav className="matrix-tabs paper-sheet">
        {(["builder", "queue", "analytics", "prompts"] as MatrixTab[]).map((item) => (
          <button key={item} className={tab === item ? "selected" : ""} onClick={() => setTab(item)}>
            {c[item]}
          </button>
        ))}
      </nav>

      {message && <p className="error-note">{message}</p>}
      {tab === "builder" && (
        <MatrixBuilder
          cards={cards}
          packs={packs}
          copy={c}
          onCreated={async (matrix) => {
            setSelectedId(matrix.id);
            setMessage(c.saved);
            await load();
            setTab("queue");
          }}
          onMessage={setMessage}
        />
      )}
      {tab === "queue" && (
        <MatrixQueue
          matrices={matrices}
          selected={selected}
          onSelect={setSelectedId}
          onChanged={() => load(matrixPage)}
          onMessage={setMessage}
          page={matrixPage}
          pages={matrixPages}
          total={matrixTotal}
          onPage={(page) => void load(page)}
          copy={c}
        />
      )}
      {tab === "analytics" && (
        <MatrixAnalyticsPanel
          matrices={matrices}
          selected={selected}
          onSelect={setSelectedId}
          copy={c}
        />
      )}
      {tab === "prompts" && <PromptVersionsPanel cards={cards} copy={c} />}
    </main>
  );
}

type Copy = typeof copy.en | typeof copy["zh-CN"];

function MatrixBuilder({
  cards,
  packs,
  copy: c,
  onCreated,
  onMessage
}: {
  cards: CharacterCard[];
  packs: TestPackView[];
  copy: Copy;
  onCreated: (matrix: MatrixView) => Promise<void>;
  onMessage: (message: string | null) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [definition, setDefinition] = useState<MatrixDefinition>(initialDefinition);
  const [modelsText, setModelsText] = useState("");
  const [temperaturesText, setTemperaturesText] = useState("");
  const [versions, setVersions] = useState<Record<string, PromptVersionView[]>>({});
  const [preview, setPreview] = useState<MatrixPreview | null>(null);
  const [draft, setDraft] = useState<MatrixView | null>(null);
  const [busy, setBusy] = useState(false);

  async function selectCard(cardId: string) {
    const exists = definition.subjects.some((item) => item.character_card_id === cardId);
    setDefinition({
      ...definition,
      subjects: exists
        ? definition.subjects.filter((item) => item.character_card_id !== cardId)
        : [...definition.subjects, { character_card_id: cardId, prompt_version_ids: [] }]
    });
    if (!exists && versions[cardId] === undefined) {
      try {
        const loaded = await workspaceApi.listPromptVersions(cardId);
        setVersions((current) => ({ ...current, [cardId]: loaded }));
      } catch {
        setVersions((current) => ({ ...current, [cardId]: [] }));
      }
    }
    setPreview(null);
  }

  function selectVersion(cardId: string, versionId: string) {
    setDefinition({
      ...definition,
      subjects: definition.subjects.map((item) =>
        item.character_card_id === cardId
          ? { ...item, prompt_version_ids: toggle(item.prompt_version_ids, versionId) }
          : item
      )
    });
    setPreview(null);
  }

  function normalizedDefinition(): MatrixDefinition {
    return {
      ...definition,
      model_overrides: modelsText.split("\n").map((item) => item.trim()).filter(Boolean),
      temperatures: temperaturesText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map(Number)
    };
  }

  function validSelection(value: MatrixDefinition): boolean {
    return Boolean(
      value.subjects.length &&
      value.test_pack_ids.length &&
      value.test_languages.length &&
      value.tester_modes.length &&
      value.judge_modes.length
    );
  }

  async function previewMatrix() {
    const next = normalizedDefinition();
    if (!validSelection(next)) {
      onMessage(c.selectRequired);
      return;
    }
    try {
      setBusy(true);
      setPreview(await workspaceApi.previewMatrix(next));
      setDefinition(next);
      setDraft(null);
      onMessage(null);
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : c.requestFailed);
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const next = normalizedDefinition();
    if (!preview || preview.task_count <= 0 || !validSelection(next)) {
      onMessage(c.confirmMismatch);
      return;
    }
    try {
      setBusy(true);
      const payload: MatrixFields = { name, description, definition: next };
      const matrix = await workspaceApi.createMatrix(payload);
      setDraft(matrix);
      await onCreated(matrix);
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : c.requestFailed);
    } finally {
      setBusy(false);
    }
  }

  async function launch() {
    if (!draft || !preview) {
      onMessage(c.confirmMismatch);
      return;
    }
    try {
      setBusy(true);
      await workspaceApi.launchMatrix(draft.id, preview.task_count);
      onMessage(c.launched);
      await onCreated(draft);
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : c.requestFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="matrix-section">
      <div className="section-heading">
        <div><p className="tape-label">{c.builder}</p><h2>{c.newMatrix}</h2></div>
      </div>
      <form className="matrix-builder paper-sheet" onSubmit={save}>
        <label>{c.matrixName}<input required value={name} onChange={(event) => setName(event.currentTarget.value)} /></label>
        <label className="matrix-wide">{c.description}<textarea rows={2} value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>

        <fieldset className="matrix-wide">
          <legend>{c.subjects}</legend>
          {cards.length === 0 ? <p>{c.noCards}</p> : (
            <div className="matrix-option-grid">
              {cards.map((card) => {
                const selected = definition.subjects.find((item) => item.character_card_id === card.id);
                return (
                  <article className={`matrix-option ${selected ? "selected" : ""}`} key={card.id}>
                    <label><input type="checkbox" checked={Boolean(selected)} onChange={() => void selectCard(card.id)} /><strong>{card.display_name}</strong></label>
                    {selected && (versions[card.id]?.length ?? 0) > 0 && (
                      <div className="version-picker">
                        {versions[card.id].map((version) => (
                          <label key={version.id}>
                            <input
                              type="checkbox"
                              checked={selected.prompt_version_ids.includes(version.id)}
                              onChange={() => selectVersion(card.id, version.id)}
                            />
                            <span>v{version.version} · {version.label}</span>
                            {version.is_active && <small>{c.active}</small>}
                          </label>
                        ))}
                        <small>{selected.prompt_version_ids.length === 0 ? c.currentConfig : ""}</small>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </fieldset>

        <fieldset className="matrix-wide">
          <legend>{c.packs}</legend>
          {packs.length === 0 ? <p>{c.noPacks}</p> : (
            <div className="matrix-option-grid compact">
              {packs.map((pack) => (
                <label className="matrix-option" key={pack.id}>
                  <input
                    type="checkbox"
                    checked={definition.test_pack_ids.includes(pack.id)}
                    onChange={() => {
                      setDefinition({ ...definition, test_pack_ids: toggle(definition.test_pack_ids, pack.id) });
                      setPreview(null);
                    }}
                  />
                  <span>{pack.name}</span><small>v{pack.version}</small>
                </label>
              ))}
            </div>
          )}
        </fieldset>

        <label>{c.models}<textarea rows={4} value={modelsText} onChange={(event) => { setModelsText(event.currentTarget.value); setPreview(null); }} /><small>{c.modelHelp}</small></label>
        <label>{c.temperatures}<input value={temperaturesText} placeholder="0.3, 0.7, 1.0" onChange={(event) => { setTemperaturesText(event.currentTarget.value); setPreview(null); }} /><small>{c.temperatureHelp}</small></label>

        <fieldset><legend>{c.languages}</legend><Checkboxes values={definition.test_languages} options={["en", "zh-CN"]} onChange={(values) => { setDefinition({ ...definition, test_languages: values as TestLanguage[] }); setPreview(null); }} /></fieldset>
        <fieldset><legend>{c.testerModes}</legend><Checkboxes values={definition.tester_modes} options={["benchmark", "adaptive"]} onChange={(values) => { setDefinition({ ...definition, tester_modes: values as TesterMode[] }); setPreview(null); }} /></fieldset>
        <fieldset><legend>{c.judgeModes}</legend><Checkboxes values={definition.judge_modes} options={["rules", "semantic", "hybrid"]} onChange={(values) => { setDefinition({ ...definition, judge_modes: values as JudgeMode[] }); setPreview(null); }} /></fieldset>

        <label>{c.repeats}<input type="number" min="1" max="10" value={definition.repeat_count} onChange={(event) => { setDefinition({ ...definition, repeat_count: Number(event.currentTarget.value) }); setPreview(null); }} /></label>
        <label>{c.concurrency}<input type="number" min="1" max="4" value={definition.concurrency} onChange={(event) => setDefinition({ ...definition, concurrency: Number(event.currentTarget.value) })} /></label>
        <label>{c.attempts}<input type="number" min="1" max="3" value={definition.max_attempts} onChange={(event) => setDefinition({ ...definition, max_attempts: Number(event.currentTarget.value) })} /></label>

        {preview && (
          <aside className={`matrix-preview matrix-wide ${preview.within_limit ? "" : "warning"}`}>
            <div><span>{c.taskCount}</span><strong>{preview.task_count}</strong></div>
            <div><span>{c.limit}</span><strong>{preview.maximum_task_count}</strong></div>
            <p>{c.runtimeCost}</p>
          </aside>
        )}

        <div className="form-actions matrix-wide">
          <button type="button" className="paper-button" disabled={busy} onClick={() => void previewMatrix()}>{c.preview}</button>
          <button className="ink-button" disabled={busy || !preview || !preview.within_limit}>{c.saveDraft}</button>
          <button type="button" className="ink-button rose" disabled={busy || !draft || !preview} onClick={() => void launch()}>{c.launch}</button>
        </div>
      </form>
    </section>
  );
}

function Checkboxes({ values, options, onChange }: { values: string[]; options: string[]; onChange: (values: string[]) => void }) {
  return <div className="inline-checks">{options.map((option) => <label key={option}><input type="checkbox" checked={values.includes(option)} onChange={() => onChange(toggle(values, option))} /><span>{option}</span></label>)}</div>;
}

function MatrixQueue({
  matrices,
  selected,
  onSelect,
  onChanged,
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
  }, [selected?.id, selected?.updated_at, taskStatus]);

  async function action(run: () => Promise<unknown>) {
    try { await run(); onMessage(null); await onChanged(); }
    catch (reason) { onMessage(reason instanceof Error ? reason.message : c.requestFailed); }
  }

  return <section className="matrix-section matrix-split">
    <aside className="matrix-list paper-sheet">
      <div className="section-heading"><h2>{c.queue}</h2><button className="paper-button" onClick={() => void onChanged()}>{c.refresh}</button></div>
      {matrices.length === 0 ? <p>{c.noMatrices}</p> : matrices.map((matrix) => (
        <button key={matrix.id} className={selected?.id === matrix.id ? "selected" : ""} onClick={() => onSelect(matrix.id)}>
          <strong>{matrix.name}</strong><span>{matrix.status}</span><small>{matrix.completed_tasks}/{matrix.total_tasks}</small>
        </button>
      ))}
      <Pagination page={page} pages={pages} total={total} onPage={onPage} />
    </aside>
    <div className="matrix-detail">
      {!selected ? <div className="paper-sheet"><p>{c.selectMatrix}</p></div> : <>
        <article className="matrix-summary paper-sheet">
          <div><p className="tape-label">{selected.status}</p><h2>{selected.name}</h2><p>{selected.description}</p></div>
          <div className="matrix-counts">
            <span>{c.pending}<strong>{selected.pending_tasks}</strong></span>
            <span>{c.running}<strong>{selected.running_tasks}</strong></span>
            <span>{c.completed}<strong>{selected.completed_tasks}</strong></span>
            <span>{c.failed}<strong>{selected.failed_tasks}</strong></span>
          </div>
          <div className="card-actions matrix-wide">
            {["queued", "running"].includes(selected.status) && <button onClick={() => void action(() => workspaceApi.pauseMatrix(selected.id))}>{c.pause}</button>}
            {["paused", "failed"].includes(selected.status) && <button onClick={() => void action(() => workspaceApi.resumeMatrix(selected.id))}>{c.resume}</button>}
            {["queued", "running", "paused"].includes(selected.status) && <button className="danger" onClick={() => void action(() => workspaceApi.cancelMatrix(selected.id))}>{c.cancel}</button>}
            {selected.failed_tasks > 0 && <button onClick={() => void action(() => workspaceApi.retryMatrix(selected.id))}>{c.retry}</button>}
            <button onClick={() => void action(() => workspaceApi.setMatrixBaseline(selected.id, !selected.is_baseline))}>{selected.is_baseline ? c.baseline : c.setBaseline}</button>
            {!["queued", "running"].includes(selected.status) && <button className="danger" onClick={() => void action(() => workspaceApi.deleteMatrix(selected.id))}>{c.remove}</button>}
          </div>
        </article>
        <div className="matrix-task-list">
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
          {(taskPage?.items ?? []).map((task) => <article className={`matrix-task paper-sheet status-${task.status}`} key={task.id}>
            <div><strong>#{task.ordinal}</strong><span>{task.status}</span></div>
            <div><span>{task.combination.test_language} · {task.combination.tester_mode} · {task.combination.judge_mode}</span><small>{task.combination.model_override ?? c.currentConfig} · T {task.combination.temperature ?? c.currentConfig} · R{task.combination.repeat_index}</small></div>
            <div><span>{c.attemptsLabel}: {task.attempt_count}/{task.max_attempts}</span><span>{task.retry_count ? `↻ ${task.retry_count}` : ""}</span></div>
            <div>{task.run_id ? <code>{task.run_id.slice(0, 12)}</code> : "—"}{task.error && <small className="task-error">{task.error}</small>}</div>
          </article>)}
          {taskPage && (
            <Pagination
              page={taskPage.page}
              pages={taskPage.pages}
              total={taskPage.total}
              onPage={(nextPage) => void loadTasks(nextPage, taskStatus)}
            />
          )}
        </div>
      </>}
    </div>
  </section>;
}

function MatrixAnalyticsPanel({ matrices, selected, onSelect, copy: c }: { matrices: MatrixView[]; selected: MatrixView | null; onSelect: (id: string) => void; copy: Copy }) {
  const [analytics, setAnalytics] = useState<MatrixAnalytics | null>(null);
  const [candidateId, setCandidateId] = useState("");
  const [comparison, setComparison] = useState<MatrixComparison | null>(null);
  useEffect(() => {
    setComparison(null);
    if (!selected) { setAnalytics(null); return; }
    void workspaceApi.matrixAnalytics(selected.id).then(setAnalytics).catch(() => setAnalytics(null));
  }, [selected?.id, selected?.updated_at]);

  const variants = useMemo(() => analytics ? [
    ...analytics.by_temperature,
    ...analytics.by_model,
    ...analytics.by_language,
    ...analytics.by_tester,
    ...analytics.by_judge
  ] : [], [analytics]);

  return <section className="matrix-section">
    <div className="analytics-toolbar paper-sheet">
      <label>{c.analytics}<select value={selected?.id ?? ""} onChange={(event) => onSelect(event.currentTarget.value)}><option value="">{c.selectMatrix}</option>{matrices.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <div className="export-links"><span>{c.exports}</span>{selected && (["json", "csv", "markdown"] as const).map((format) => <a key={format} href={workspaceApi.matrixExportUrl(selected.id, format)}>{format.toUpperCase()}</a>)}</div>
    </div>
    {!analytics || analytics.completed_runs === 0 ? <div className="empty-library paper-sheet"><p>{c.noAnalytics}</p></div> : <>
      <div className="metric-grid">
        <Metric label={c.score} value={score(analytics.mean_score)} />
        <Metric label={c.passRate} value={percent(analytics.pass_rate)} />
        <Metric label={c.reviewRate} value={percent(analytics.review_rate)} />
        <Metric label={c.failureRate} value={percent(analytics.failure_rate)} />
        <Metric label={c.deviation} value={score(analytics.standard_deviation)} />
        <Metric label={c.tokens} value={`${analytics.input_tokens} / ${analytics.output_tokens}`} />
        <Metric label={c.latency} value={`${analytics.latency_ms} ms`} />
        <Metric label={c.tasks} value={`${analytics.completed_runs}/${analytics.total_tasks}`} />
      </div>
      <article className="variant-table paper-sheet"><h3>{c.variants}</h3><table><thead><tr><th>Variant</th><th>{c.run}</th><th>{c.score}</th><th>{c.passRate}</th><th>{c.reviewRate}</th><th>{c.failureRate}</th></tr></thead><tbody>{variants.map((item) => <tr key={item.key}><td>{item.label}</td><td>{item.run_count}</td><td>{score(item.mean_score)}</td><td>{percent(item.pass_rate)}</td><td>{percent(item.review_rate)}</td><td>{percent(item.failure_rate)}</td></tr>)}</tbody></table></article>
      <article className="comparison-card paper-sheet">
        <h3>{c.compare}</h3>
        <label>{c.compareWith}<select value={candidateId} onChange={(event) => setCandidateId(event.currentTarget.value)}><option value="">—</option>{matrices.filter((item) => item.id !== selected?.id).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <button className="ink-button" disabled={!selected || !candidateId} onClick={() => selected && void workspaceApi.compareMatrices(selected.id, candidateId).then(setComparison)}>{c.compare}</button>
        {comparison && <div className={`comparison-result ${comparison.classification}`}><strong>{c.classification}: {comparison.classification}</strong><span>Δ {c.score}: {score(comparison.score_delta)}</span><span>Δ {c.passRate}: {percent(comparison.pass_rate_delta)}</span>{comparison.incompatibilities.length > 0 && <p>{c.incompatible}: {comparison.incompatibilities.join(", ")}</p>}</div>}
      </article>
    </>}
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className="metric-card paper-sheet"><span>{label}</span><strong>{value}</strong></article>;
}

function PromptVersionsPanel({ cards, copy: c }: { cards: CharacterCard[]; copy: Copy }) {
  const [cardId, setCardId] = useState(cards[0]?.id ?? "");
  const [versions, setVersions] = useState<PromptVersionView[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [diff, setDiff] = useState<PromptVersionDiff | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load(id = cardId) {
    if (!id) { setVersions([]); return; }
    try { setVersions(await workspaceApi.listPromptVersions(id)); setMessage(null); }
    catch (reason) { setVersions([]); setMessage(reason instanceof Error ? reason.message : c.requestFailed); }
  }
  useEffect(() => { void load(cardId); }, [cardId]);

  return <section className="matrix-section">
    <div className="section-heading"><div><p className="tape-label rose">{c.prompts}</p><h2>{c.prompts}</h2></div></div>
    <div className="prompt-version-toolbar paper-sheet"><label>{c.promptCard}<select value={cardId} onChange={(event) => { setCardId(event.currentTarget.value); setDiff(null); }}><option value="">—</option>{cards.map((card) => <option value={card.id} key={card.id}>{card.display_name}</option>)}</select></label></div>
    {message && <p className="error-note">{message}</p>}
    {versions.length === 0 ? <div className="empty-library paper-sheet"><p>{c.noPromptVersions}</p></div> : <>
      <div className="prompt-version-list">{versions.map((version) => <article className={`prompt-version-card paper-sheet ${version.is_active ? "active" : ""}`} key={version.id}><div><span>{c.version} {version.version}</span><h3>{version.label}</h3></div><div className="version-badges">{version.is_active && <span>{c.active}</span>}{version.is_production && <span>{c.production}</span>}</div><dl><div><dt>Model</dt><dd>{version.model}</dd></div><div><dt>Temperature</dt><dd>{version.temperature}</dd></div><div><dt>Provider</dt><dd>{version.provider}</dd></div></dl><pre>{version.system_prompt}</pre><div className="card-actions"><button disabled={version.is_active} onClick={() => void workspaceApi.restorePromptVersion(cardId, version.id).then(() => load())}>{c.restore}</button><button onClick={() => void workspaceApi.setProductionPromptVersion(cardId, version.id, !version.is_production).then(() => load())}>{version.is_production ? c.unmarkProduction : c.markProduction}</button></div></article>)}</div>
      <article className="prompt-diff paper-sheet"><h3>{c.compareVersions}</h3><div><select value={leftId} onChange={(event) => setLeftId(event.currentTarget.value)}><option value="">—</option>{versions.map((item) => <option value={item.id} key={item.id}>v{item.version}</option>)}</select><select value={rightId} onChange={(event) => setRightId(event.currentTarget.value)}><option value="">—</option>{versions.map((item) => <option value={item.id} key={item.id}>v{item.version}</option>)}</select><button className="ink-button" disabled={!leftId || !rightId || leftId === rightId} onClick={() => void workspaceApi.comparePromptVersions(leftId, rightId).then(setDiff)}>{c.compareVersions}</button></div>{diff && <><p>{c.changedFields}: {diff.changed_fields.join(", ") || "—"}</p><div className="prompt-diff-grid"><div><h4>{c.promptBefore}</h4><pre>{diff.system_prompt_before}</pre></div><div><h4>{c.promptAfter}</h4><pre>{diff.system_prompt_after}</pre></div></div></>}</article>
    </>}
  </section>;
}
