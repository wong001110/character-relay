import { useEffect, useMemo, useState } from "react";

import { calibrationApi, type CalibrationDatasetView } from "./calibrationApi";
import {
  evaluationApi,
  type ClassificationMetrics,
  type EvaluationMode,
  type JudgeEvaluationView
} from "./evaluationApi";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import "./evaluation.css";

interface Props { onClose: () => void; }

const copy = {
  en: {
    title: "Judge Evaluation Analytics",
    subtitle: "Measure Rules, Semantic, and Hybrid predictions against approved human ground truth.",
    back: "Character Library", dataset: "Approved Dataset", modes: "Judge modes", run: "Run Evaluation",
    running: "Evaluating…", history: "Evaluation Snapshots", empty: "No Evaluation Snapshots yet.",
    version: "Version", status: "Status", accuracy: "Accuracy", f1: "Macro F1", fp: "False positive",
    fn: "False negative", eligible: "Eligible", agreement: "Rules / Semantic agreement",
    confusion: "Confusion Matrix", predictions: "Case Predictions", expected: "Expected", predicted: "Predicted",
    source: "Contract source", error: "Error", completed: "Evaluation completed.", failed: "Evaluation failed."
  },
  "zh-CN": {
    title: "Judge 评测分析", subtitle: "用人工批准的 Ground Truth 衡量 Rules、Semantic 与 Hybrid。",
    back: "返回角色库", dataset: "已批准 Dataset", modes: "Judge 模式", run: "执行评测",
    running: "评测中…", history: "Evaluation Snapshots", empty: "还没有 Evaluation Snapshot。",
    version: "版本", status: "状态", accuracy: "准确率", f1: "Macro F1", fp: "误杀率",
    fn: "漏检率", eligible: "有效样本", agreement: "Rules / Semantic 一致率",
    confusion: "混淆矩阵", predictions: "逐 Case 预测", expected: "人工标准", predicted: "预测",
    source: "合同来源", error: "错误", completed: "评测已完成。", failed: "评测失败。"
  }
} as const;

const modes: EvaluationMode[] = ["rules", "semantic", "hybrid"];

export function EvaluationLab({ onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [datasets, setDatasets] = useState<CalibrationDatasetView[]>([]);
  const [evaluations, setEvaluations] = useState<JudgeEvaluationView[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [selectedModes, setSelectedModes] = useState<EvaluationMode[]>([...modes]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const approved = datasets.filter((item) => item.status === "approved");
  const active = evaluations.find((item) => item.id === activeId) ?? evaluations[0] ?? null;

  async function load(preferred?: string) {
    const [nextDatasets, nextEvaluations] = await Promise.all([
      calibrationApi.list(), evaluationApi.list()
    ]);
    setDatasets(nextDatasets);
    setEvaluations(nextEvaluations);
    setDatasetId((current) => current || nextDatasets.find((item) => item.status === "approved")?.id || "");
    setActiveId(preferred ?? activeId ?? nextEvaluations[0]?.id ?? null);
  }

  useEffect(() => { void load(); }, []);

  async function runEvaluation() {
    if (!datasetId || selectedModes.length === 0) return;
    try {
      setWorking(true); setMessage(null);
      const created = await evaluationApi.run(datasetId, selectedModes);
      await load(created.id); setMessage(c.completed);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : c.failed);
    } finally { setWorking(false); }
  }

  return <main className="evaluation-page">
    <header className="evaluation-header"><div><p className="kicker">Echo Masque · Phase 16</p><h1>{c.title}</h1><p>{c.subtitle}</p></div><div className="header-actions"><LanguageSwitcher /><button className="paper-button" onClick={onClose}>{c.back}</button></div></header>
    {message && <p className="paper-sheet evaluation-message">{message}</p>}
    <section className="evaluation-launch paper-sheet">
      <label>{c.dataset}<select value={datasetId} onChange={(e) => setDatasetId(e.currentTarget.value)}><option value="" disabled>—</option>{approved.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}</select></label>
      <fieldset><legend>{c.modes}</legend>{modes.map((mode) => <label key={mode}><input type="checkbox" checked={selectedModes.includes(mode)} onChange={(e) => setSelectedModes(e.currentTarget.checked ? [...selectedModes, mode] : selectedModes.filter((item) => item !== mode))} />{mode}</label>)}</fieldset>
      <button className="ink-button" disabled={working || !datasetId || selectedModes.length === 0} onClick={() => void runEvaluation()}>{working ? c.running : c.run}</button>
    </section>
    <section className="evaluation-layout">
      <aside className="evaluation-history"><h2>{c.history}</h2>{evaluations.length === 0 ? <div className="paper-sheet">{c.empty}</div> : evaluations.map((item) => <button key={item.id} className={`paper-sheet evaluation-history-item ${active?.id === item.id ? "active" : ""}`} onClick={() => setActiveId(item.id)}><strong>{item.dataset_name}</strong><span>{c.version} {item.dataset_version} · {item.status}</span><small>{new Date(item.created_at).toLocaleString()}</small></button>)}</aside>
      {active && <section className="evaluation-report paper-sheet"><div className="evaluation-report-head"><div><span className={`status-chip ${active.status}`}>{active.status}</span><h2>{active.dataset_name}</h2><p>v{active.dataset_version} · {active.modes.join(" / ")}</p></div><Agreement value={active.metrics.rules_semantic_agreement.agreement_rate} label={c.agreement} /></div>
        <div className="metric-grid">{modes.map((mode) => <MetricCard key={mode} mode={mode} metrics={active.metrics.by_mode[mode]} copy={c} />)}</div>
        <h3>{c.confusion}</h3><Confusion metrics={active.metrics.by_mode.hybrid} />
        <h3>{c.predictions}</h3><div className="prediction-list">{active.predictions.map((item) => <article key={item.id}><div><span className={`verdict ${item.expected_verdict.toLowerCase()}`}>{c.expected}: {item.expected_verdict}</span><span className={`verdict ${(item.predicted_verdict ?? "review").toLowerCase()}`}>{c.predicted}: {item.predicted_verdict ?? "—"}</span><strong>{item.mode}</strong></div><small>{c.source}: {item.contract_source}</small>{item.error && <p className="prediction-error">{c.error}: {item.error}</p>}</article>)}</div>
      </section>}
    </section>
  </main>;
}

function MetricCard({ mode, metrics, copy: c }: { mode: EvaluationMode; metrics: ClassificationMetrics; copy: typeof copy.en | typeof copy["zh-CN"] }) {
  return <article className="metric-card"><h3>{mode}</h3><strong>{Math.round(metrics.accuracy * 100)}%</strong><span>{c.accuracy}</span><dl><div><dt>{c.f1}</dt><dd>{metrics.macro_f1.toFixed(3)}</dd></div><div><dt>{c.fp}</dt><dd>{Math.round(metrics.false_positive_rate * 100)}%</dd></div><div><dt>{c.fn}</dt><dd>{Math.round(metrics.false_negative_rate * 100)}%</dd></div><div><dt>{c.eligible}</dt><dd>{metrics.eligible}</dd></div></dl></article>;
}

function Agreement({ value, label }: { value: number; label: string }) { return <div className="agreement-badge"><strong>{Math.round(value * 100)}%</strong><span>{label}</span></div>; }

function Confusion({ metrics }: { metrics: ClassificationMetrics }) {
  const labels = ["PASS", "FAIL", "REVIEW"];
  return <div className="confusion-grid"><span /><strong>→ PASS</strong><strong>→ FAIL</strong><strong>→ REVIEW</strong>{labels.map((expected) => <FragmentRow key={expected} expected={expected} values={metrics.confusion[expected]} />)}</div>;
}

function FragmentRow({ expected, values }: { expected: string; values: Record<string, number> }) { return <><strong>{expected}</strong><span>{values.PASS ?? 0}</span><span>{values.FAIL ?? 0}</span><span>{values.REVIEW ?? 0}</span></>; }
