import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import {
  calibrationApi,
  type CalibrationArchive,
  type CalibrationCaseFields,
  type CalibrationDatasetView,
  type CalibrationRunImport,
  type CalibrationVerdict,
  type CoverageDimension
} from "./calibrationApi";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import "./calibration.css";

interface Props { onClose: () => void; }

const dimensions: CoverageDimension[] = [
  "identity", "memory", "instruction_resistance", "capability_honesty", "persona", "language"
];

const copy = {
  en: {
    title: "Calibration Lab", subtitle: "Preserve human-approved expected verdicts and exact evidence.",
    back: "Character Library", create: "Create Dataset", name: "Dataset name", description: "Description",
    approve: "Approve", archive: "Archive", next: "New version", remove: "Delete", cases: "Cases",
    manual: "Manual Case", run: "Import Run Turn", scenario: "Scenario name", category: "Category",
    language: "Language", tester: "Tester message", response: "Subject response", verdict: "Expected verdict",
    failure: "Failure type", evidence: "Exact evidence excerpt", notes: "Notes", coverage: "Coverage",
    add: "Add Case", runId: "Run ID", scenarioId: "Scenario ID", turn: "Turn index", import: "Import Turn",
    empty: "No Calibration Datasets yet.", immutable: "Approved and archived versions are immutable.",
    export: "Download Archive", importArchive: "Import Archive", replace: "Replace existing Calibration data",
    status: "Status", version: "Version", source: "Source", working: "Working…", completed: "Operation completed.",
    error: "Calibration operation failed."
  },
  "zh-CN": {
    title: "校准数据实验室", subtitle: "保存人工批准的预期结论与精确证据。", back: "返回角色库",
    create: "创建 Dataset", name: "Dataset 名称", description: "说明", approve: "批准", archive: "归档",
    next: "新版本", remove: "删除", cases: "Cases", manual: "手动 Case", run: "从 Run Turn 导入",
    scenario: "Scenario 名称", category: "类别", language: "语言", tester: "Tester 消息",
    response: "Subject 回答", verdict: "预期结论", failure: "失败类型", evidence: "精确证据片段",
    notes: "备注", coverage: "覆盖维度", add: "加入 Case", runId: "Run ID", scenarioId: "Scenario ID",
    turn: "Turn Index", import: "导入 Turn", empty: "还没有 Calibration Dataset。",
    immutable: "批准或归档后的版本不可修改。", export: "下载 Archive", importArchive: "导入 Archive",
    replace: "替换现有 Calibration 数据", status: "状态", version: "版本", source: "来源",
    working: "处理中…", completed: "操作已完成。", error: "Calibration 操作失败。"
  }
} as const;

function emptyCase(): CalibrationCaseFields {
  return {
    scenario_id: null, character_card_id: null, scenario_name: "", scenario_category: "identity_integrity",
    language: "en", turn_index: null, tester_message: "", subject_response: "", expected_verdict: "PASS",
    failure_type: "", evidence_excerpt: "", coverage_dimensions: [], notes: ""
  };
}

function emptyRun(): CalibrationRunImport {
  return { run_id: "", scenario_id: "", turn_index: 1, expected_verdict: "PASS", failure_type: "", evidence_excerpt: "", coverage_dimensions: [], notes: "" };
}

export function CalibrationLab({ onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [datasets, setDatasets] = useState<CalibrationDatasetView[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [manual, setManual] = useState<CalibrationCaseFields>(emptyCase());
  const [runImport, setRunImport] = useState<CalibrationRunImport>(emptyRun());
  const [replace, setReplace] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const active = datasets.find((item) => item.id === activeId) ?? datasets[0] ?? null;

  async function load(preferred?: string) {
    const next = await calibrationApi.list();
    setDatasets(next);
    setActiveId(preferred ?? activeId ?? next[0]?.id ?? null);
  }

  useEffect(() => { void run(async () => { await load(); }, ""); }, []);

  async function run(action: () => Promise<void>, success: string = c.completed) {
    try { setWorking(true); setMessage(null); await action(); if (success) setMessage(success); }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : c.error); }
    finally { setWorking(false); }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    await run(async () => { const item = await calibrationApi.create(name, description); setName(""); setDescription(""); await load(item.id); });
  }

  async function addManual(event: FormEvent) {
    event.preventDefault(); if (!active) return;
    await run(async () => { await calibrationApi.createCase(active.id, manual); setManual(emptyCase()); await load(active.id); });
  }

  async function addRun(event: FormEvent) {
    event.preventDefault(); if (!active) return;
    await run(async () => { await calibrationApi.importRun(active.id, runImport); setRunImport(emptyRun()); await load(active.id); });
  }

  async function exportArchive() {
    await run(async () => {
      const archive = await calibrationApi.exportArchive();
      const blob = new Blob([JSON.stringify(archive, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = `echo-masque-calibration-${new Date().toISOString().slice(0, 10)}.json`;
      link.click(); URL.revokeObjectURL(url);
    });
  }

  async function importArchive(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]; if (!file) return;
    await run(async () => { const archive = JSON.parse(await file.text()) as CalibrationArchive; await calibrationApi.importArchive(archive, replace ? "replace" : "merge"); await load(); });
    event.currentTarget.value = "";
  }

  const editable = active?.status === "draft";
  return <main className="calibration-page">
    <header className="calibration-header"><div><p className="kicker">Echo Masque · Phase 16</p><h1>{c.title}</h1><p>{c.subtitle}</p></div><div className="header-actions"><LanguageSwitcher /><button className="paper-button" onClick={onClose}>{c.back}</button></div></header>
    {message && <p className="paper-sheet calibration-message">{message}</p>}
    <section className="calibration-toolbar paper-sheet">
      <form onSubmit={create}><input value={name} onChange={(e) => setName(e.currentTarget.value)} placeholder={c.name} required /><input value={description} onChange={(e) => setDescription(e.currentTarget.value)} placeholder={c.description} /><button className="ink-button" disabled={working}>{c.create}</button></form>
      <div className="archive-actions"><button className="paper-button" onClick={() => void exportArchive()}>{c.export}</button><label className="paper-button file-button">{c.importArchive}<input type="file" accept="application/json" onChange={(e) => void importArchive(e)} /></label><label className="replace-check"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.currentTarget.checked)} />{c.replace}</label></div>
    </section>
    <section className="calibration-layout">
      <aside className="dataset-list">{datasets.length === 0 ? <div className="paper-sheet">{c.empty}</div> : datasets.map((item) => <button key={item.id} className={`paper-sheet dataset-button ${active?.id === item.id ? "active" : ""}`} onClick={() => setActiveId(item.id)}><strong>{item.name}</strong><span>{c.version} {item.version} · {item.status}</span><small>{item.cases.length} {c.cases}</small></button>)}</aside>
      {active && <section className="dataset-detail paper-sheet">
        <div className="dataset-head"><div><span className={`status-chip ${active.status}`}>{active.status}</span><h2>{active.name}</h2><p>{active.description}</p></div><div className="dataset-actions">{active.status === "draft" && <><button className="ink-button" disabled={working || active.cases.length === 0} onClick={() => void run(async () => { await calibrationApi.approve(active.id); await load(active.id); })}>{c.approve}</button><button className="paper-button danger-button" onClick={() => void run(async () => { await calibrationApi.remove(active.id); await load(); })}>{c.remove}</button></>}{active.status !== "archived" && <button className="paper-button" onClick={() => void run(async () => { await calibrationApi.archive(active.id); await load(active.id); })}>{c.archive}</button>}{active.status !== "draft" && <button className="paper-button" onClick={() => void run(async () => { const next = await calibrationApi.nextVersion(active.id); await load(next.id); })}>{c.next}</button>}</div></div>
        {!editable && <p className="immutable-note">{c.immutable}</p>}
        {editable && <div className="case-forms">
          <CaseForm title={c.manual} copy={c} value={manual} onChange={setManual} onSubmit={addManual} working={working} />
          <RunForm copy={c} value={runImport} onChange={setRunImport} onSubmit={addRun} working={working} />
        </div>}
        <div className="case-list">{active.cases.map((item) => <article key={item.id} className="calibration-case"><div><span className={`verdict ${item.expected_verdict.toLowerCase()}`}>{item.expected_verdict}</span><strong>{item.scenario_name}</strong><small>{c.source}: {item.source} · {item.language} · {item.scenario_category}</small></div><p>{item.subject_response}</p>{item.evidence_excerpt && <blockquote>{item.evidence_excerpt}</blockquote>}<div className="dimension-row">{item.coverage_dimensions.map((dimension) => <span key={dimension}>{dimension}</span>)}</div>{editable && <button className="paper-button danger-button" onClick={() => void run(async () => { await calibrationApi.removeCase(item.id); await load(active.id); })}>{c.remove}</button>}</article>)}</div>
      </section>}
    </section>
    {working && <p className="working-note">{c.working}</p>}
  </main>;
}

function CaseForm({ title, copy: c, value, onChange, onSubmit, working }: { title: string; copy: typeof copy.en | typeof copy["zh-CN"]; value: CalibrationCaseFields; onChange: (value: CalibrationCaseFields) => void; onSubmit: (event: FormEvent) => void; working: boolean }) {
  return <form className="case-form" onSubmit={onSubmit}><h3>{title}</h3><input value={value.scenario_name} onChange={(e) => onChange({ ...value, scenario_name: e.currentTarget.value })} placeholder={c.scenario} required /><input value={value.scenario_category} onChange={(e) => onChange({ ...value, scenario_category: e.currentTarget.value })} placeholder={c.category} required /><select value={value.language} onChange={(e) => onChange({ ...value, language: e.currentTarget.value as "en" | "zh-CN" })}><option value="en">English</option><option value="zh-CN">简体中文</option></select><textarea value={value.tester_message} onChange={(e) => onChange({ ...value, tester_message: e.currentTarget.value })} placeholder={c.tester} /><textarea value={value.subject_response} onChange={(e) => onChange({ ...value, subject_response: e.currentTarget.value })} placeholder={c.response} required /><VerdictFields copy={c} verdict={value.expected_verdict} failure={value.failure_type} evidence={value.evidence_excerpt} onVerdict={(next) => onChange({ ...value, expected_verdict: next })} onFailure={(next) => onChange({ ...value, failure_type: next })} onEvidence={(next) => onChange({ ...value, evidence_excerpt: next })} /><DimensionChecks copy={c} selected={value.coverage_dimensions} onChange={(next) => onChange({ ...value, coverage_dimensions: next })} /><textarea value={value.notes} onChange={(e) => onChange({ ...value, notes: e.currentTarget.value })} placeholder={c.notes} /><button className="ink-button" disabled={working}>{c.add}</button></form>;
}

function RunForm({ copy: c, value, onChange, onSubmit, working }: { copy: typeof copy.en | typeof copy["zh-CN"]; value: CalibrationRunImport; onChange: (value: CalibrationRunImport) => void; onSubmit: (event: FormEvent) => void; working: boolean }) {
  return <form className="case-form" onSubmit={onSubmit}><h3>{c.run}</h3><input value={value.run_id} onChange={(e) => onChange({ ...value, run_id: e.currentTarget.value })} placeholder={c.runId} required /><input value={value.scenario_id} onChange={(e) => onChange({ ...value, scenario_id: e.currentTarget.value })} placeholder={c.scenarioId} required /><input type="number" min="1" value={value.turn_index} onChange={(e) => onChange({ ...value, turn_index: Number(e.currentTarget.value) })} placeholder={c.turn} /><VerdictFields copy={c} verdict={value.expected_verdict} failure={value.failure_type} evidence={value.evidence_excerpt} onVerdict={(next) => onChange({ ...value, expected_verdict: next })} onFailure={(next) => onChange({ ...value, failure_type: next })} onEvidence={(next) => onChange({ ...value, evidence_excerpt: next })} /><DimensionChecks copy={c} selected={value.coverage_dimensions} onChange={(next) => onChange({ ...value, coverage_dimensions: next })} /><textarea value={value.notes} onChange={(e) => onChange({ ...value, notes: e.currentTarget.value })} placeholder={c.notes} /><button className="ink-button" disabled={working}>{c.import}</button></form>;
}

function VerdictFields({ copy: c, verdict, failure, evidence, onVerdict, onFailure, onEvidence }: { copy: typeof copy.en | typeof copy["zh-CN"]; verdict: CalibrationVerdict; failure: string; evidence: string; onVerdict: (value: CalibrationVerdict) => void; onFailure: (value: string) => void; onEvidence: (value: string) => void }) {
  return <><select value={verdict} onChange={(e) => onVerdict(e.currentTarget.value as CalibrationVerdict)}><option>PASS</option><option>FAIL</option><option>REVIEW</option></select>{verdict !== "PASS" && <><input value={failure} onChange={(e) => onFailure(e.currentTarget.value)} placeholder={c.failure} required /><textarea value={evidence} onChange={(e) => onEvidence(e.currentTarget.value)} placeholder={c.evidence} required /></>}</>;
}

function DimensionChecks({ copy: c, selected, onChange }: { copy: typeof copy.en | typeof copy["zh-CN"]; selected: CoverageDimension[]; onChange: (value: CoverageDimension[]) => void }) {
  return <fieldset><legend>{c.coverage}</legend>{dimensions.map((item) => <label key={item}><input type="checkbox" checked={selected.includes(item)} onChange={(e) => onChange(e.currentTarget.checked ? [...selected, item] : selected.filter((value) => value !== item))} />{item}</label>)}</fieldset>;
}
