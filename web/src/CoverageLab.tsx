import { useEffect, useMemo, useState } from "react";

import type { CharacterCard, TestLanguage } from "./api";
import { authoringApi } from "./authoringApi";
import { calibrationApi, type CalibrationDatasetView } from "./calibrationApi";
import {
  coverageApi,
  type DatasetCoverageReport,
  type RubricComparisonReport
} from "./coverageApi";
import { evaluationApi, type JudgeEvaluationView } from "./evaluationApi";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import "./coverage.css";

interface Props {
  cards: CharacterCard[];
  onClose: () => void;
}

const copy = {
  en: {
    title: "Rubric & Coverage Lab",
    subtitle: "Compare Semantic rubrics on one frozen Dataset and expose untested risks.",
    back: "Character Library",
    dataset: "Approved Dataset",
    evaluation: "Semantic Evaluation Snapshot",
    load: "Analyze coverage",
    coverage: "Six-dimension coverage",
    missing: "Missing",
    weak: "Weak",
    covered: "Covered",
    cases: "Cases",
    semantic: "Semantic average",
    suggestions: "Authoring gap suggestions",
    character: "Character for AI drafts",
    language: "Draft language",
    generate: "Generate AI Drafts from gaps",
    generated: "AI drafts were created for review. Nothing was approved automatically.",
    baseline: "Baseline Rubric Snapshot",
    candidate: "Candidate Rubric Snapshot",
    compare: "Compare rubrics",
    comparison: "Rubric comparison",
    accuracy: "Accuracy delta",
    f1: "Macro F1 delta",
    fp: "False-positive delta",
    fn: "False-negative delta",
    dimensions: "Dimension score deltas",
    changes: "Prediction changes",
    empty: "Create and approve a Calibration Dataset first.",
    working: "Working…"
  },
  "zh-CN": {
    title: "Rubric 与覆盖分析",
    subtitle: "在同一冻结 Dataset 上比较 Semantic Rubric，并找出尚未测试的风险。",
    back: "返回角色库",
    dataset: "已批准 Dataset",
    evaluation: "Semantic Evaluation Snapshot",
    load: "分析覆盖率",
    coverage: "六维覆盖情况",
    missing: "缺失",
    weak: "薄弱",
    covered: "已覆盖",
    cases: "Cases",
    semantic: "Semantic 平均分",
    suggestions: "Authoring 缺口建议",
    character: "生成 AI Draft 的角色",
    language: "Draft 语言",
    generate: "根据缺口生成 AI Draft",
    generated: "AI Draft 已建立，仍需人工审核；系统没有自动批准。",
    baseline: "Baseline Rubric Snapshot",
    candidate: "Candidate Rubric Snapshot",
    compare: "比较 Rubric",
    comparison: "Rubric 比较结果",
    accuracy: "Accuracy 差值",
    f1: "Macro F1 差值",
    fp: "误杀率差值",
    fn: "漏检率差值",
    dimensions: "维度分数差值",
    changes: "预测变化",
    empty: "请先建立并批准 Calibration Dataset。",
    working: "处理中…"
  }
} as const;

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

export function CoverageLab({ cards, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [datasets, setDatasets] = useState<CalibrationDatasetView[]>([]);
  const [evaluations, setEvaluations] = useState<JudgeEvaluationView[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [evaluationId, setEvaluationId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [cardId, setCardId] = useState(cards[0]?.id ?? "");
  const [draftLanguage, setDraftLanguage] = useState<TestLanguage>("en");
  const [coverage, setCoverage] = useState<DatasetCoverageReport | null>(null);
  const [comparison, setComparison] = useState<RubricComparisonReport | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const approved = datasets.filter((item) => item.status === "approved");
  const datasetEvaluations = useMemo(
    () => evaluations.filter((item) => item.dataset_id === datasetId),
    [evaluations, datasetId]
  );

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [nextDatasets, nextEvaluations] = await Promise.all([
          calibrationApi.list(),
          evaluationApi.list()
        ]);
        if (!active) return;
        const nextApproved = nextDatasets.filter((item) => item.status === "approved");
        setDatasets(nextDatasets);
        setEvaluations(nextEvaluations);
        setDatasetId((current) => current || nextApproved[0]?.id || "");
      } catch (reason) {
        if (active) setMessage(reason instanceof Error ? reason.message : String(reason));
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const related = evaluations.filter((item) => item.dataset_id === datasetId);
    setEvaluationId(related[0]?.id ?? "");
    setBaselineId(related[1]?.id ?? related[0]?.id ?? "");
    setCandidateId(related[0]?.id ?? "");
    setCoverage(null);
    setComparison(null);
  }, [datasetId, evaluations]);

  async function analyze() {
    if (!datasetId) return;
    try {
      setWorking(true);
      setMessage(null);
      setCoverage(await coverageApi.report(datasetId, evaluationId || undefined));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function compare() {
    if (!baselineId || !candidateId) return;
    try {
      setWorking(true);
      setMessage(null);
      setComparison(await coverageApi.compare(baselineId, candidateId));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function generateDrafts() {
    if (!coverage || !cardId || coverage.suggestions.length === 0) return;
    const riskTags = [...new Set(coverage.suggestions.flatMap((item) => item.risk_tags))];
    const scenarioCount = Math.min(
      8,
      coverage.suggestions.reduce((total, item) => total + item.recommended_count, 0)
    );
    try {
      setWorking(true);
      setMessage(null);
      await authoringApi.generate({
        character_card_id: cardId,
        language: draftLanguage,
        risk_tags: riskTags,
        known_failures: [],
        instructions: `Draft reviewable Scenarios for these approved Dataset coverage gaps: ${coverage.suggestions.map((item) => item.dimension).join(", ")}. Do not claim ground truth.`,
        scenario_count: Math.max(1, scenarioCount),
        include_test_pack: true
      });
      setMessage(c.generated);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="coverage-page">
      <header className="coverage-header">
        <div>
          <p className="kicker">Echo Masque · Phase 16E</p>
          <h1>{c.title}</h1>
          <p>{c.subtitle}</p>
        </div>
        <div className="header-actions">
          <LanguageSwitcher />
          <button type="button" className="paper-button" onClick={onClose}>{c.back}</button>
        </div>
      </header>

      {message && <p className="paper-sheet coverage-message">{message}</p>}
      {approved.length === 0 ? (
        <section className="paper-sheet coverage-empty"><h2>{c.empty}</h2></section>
      ) : (
        <>
          <section className="paper-sheet coverage-controls">
            <label>{c.dataset}
              <select value={datasetId} onChange={(event) => setDatasetId(event.currentTarget.value)}>
                {approved.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}
              </select>
            </label>
            <label>{c.evaluation}
              <select value={evaluationId} onChange={(event) => setEvaluationId(event.currentTarget.value)}>
                <option value="">—</option>
                {datasetEvaluations.map((item) => <option key={item.id} value={item.id}>{item.created_at} · {item.status}</option>)}
              </select>
            </label>
            <button type="button" className="ink-button" onClick={() => void analyze()} disabled={working}>
              {working ? c.working : c.load}
            </button>
          </section>

          {coverage && (
            <section className="coverage-section">
              <h2>{c.coverage}</h2>
              <div className="coverage-grid">
                {coverage.dimensions.map((item) => (
                  <article className={`paper-sheet coverage-card status-${item.status}`} key={item.dimension}>
                    <span className="coverage-status">{item.status === "missing" ? c.missing : item.status === "weak" ? c.weak : c.covered}</span>
                    <h3>{item.dimension.replaceAll("_", " ")}</h3>
                    <strong>{item.case_count} {c.cases}</strong>
                    <p>PASS {item.pass_count} · FAIL {item.fail_count} · REVIEW {item.review_count}</p>
                    <p>{c.semantic}: {item.semantic_average_score ?? "—"}</p>
                  </article>
                ))}
              </div>

              {coverage.suggestions.length > 0 && (
                <div className="paper-sheet coverage-suggestions">
                  <h3>{c.suggestions}</h3>
                  {coverage.suggestions.map((item) => (
                    <div className="coverage-suggestion" key={item.dimension}>
                      <strong>{item.dimension.replaceAll("_", " ")}</strong>
                      <span>{item.reason}</span>
                      <small>{item.risk_tags.join(" · ")}</small>
                    </div>
                  ))}
                  <div className="coverage-authoring">
                    <label>{c.character}
                      <select value={cardId} onChange={(event) => setCardId(event.currentTarget.value)}>
                        {cards.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                      </select>
                    </label>
                    <label>{c.language}
                      <select value={draftLanguage} onChange={(event) => setDraftLanguage(event.currentTarget.value as TestLanguage)}>
                        <option value="en">English</option>
                        <option value="zh-CN">简体中文</option>
                      </select>
                    </label>
                    <button type="button" className="ink-button" disabled={working || !cardId} onClick={() => void generateDrafts()}>{c.generate}</button>
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="paper-sheet rubric-controls">
            <label>{c.baseline}
              <select value={baselineId} onChange={(event) => setBaselineId(event.currentTarget.value)}>
                <option value="">—</option>
                {datasetEvaluations.map((item) => <option key={item.id} value={item.id}>{item.created_at}</option>)}
              </select>
            </label>
            <label>{c.candidate}
              <select value={candidateId} onChange={(event) => setCandidateId(event.currentTarget.value)}>
                <option value="">—</option>
                {datasetEvaluations.map((item) => <option key={item.id} value={item.id}>{item.created_at}</option>)}
              </select>
            </label>
            <button type="button" className="ink-button" disabled={working || !baselineId || !candidateId} onClick={() => void compare()}>{c.compare}</button>
          </section>

          {comparison && (
            <section className="coverage-section rubric-report">
              <h2>{c.comparison} · {comparison.classification}</h2>
              <div className="rubric-metrics">
                <article className="paper-sheet"><span>{c.accuracy}</span><strong>{signed(comparison.accuracy_delta)}</strong></article>
                <article className="paper-sheet"><span>{c.f1}</span><strong>{signed(comparison.macro_f1_delta)}</strong></article>
                <article className="paper-sheet"><span>{c.fp}</span><strong>{signed(comparison.false_positive_rate_delta)}</strong></article>
                <article className="paper-sheet"><span>{c.fn}</span><strong>{signed(comparison.false_negative_rate_delta)}</strong></article>
              </div>
              <div className="paper-sheet rubric-table-wrap">
                <h3>{c.dimensions}</h3>
                <table><thead><tr><th>Dimension</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr></thead><tbody>
                  {comparison.dimension_deltas.map((item) => <tr key={item.dimension}><td>{item.dimension}</td><td>{item.baseline_average ?? "—"}</td><td>{item.candidate_average ?? "—"}</td><td>{item.delta === null ? "—" : signed(item.delta)}</td></tr>)}
                </tbody></table>
              </div>
              <div className="paper-sheet rubric-table-wrap">
                <h3>{c.changes}</h3>
                <p>{comparison.baseline_rubric_version} → {comparison.candidate_rubric_version}</p>
                <p>Baseline {percent(comparison.baseline_metrics.accuracy)} · Candidate {percent(comparison.candidate_metrics.accuracy)}</p>
                <table><thead><tr><th>Case</th><th>Expected</th><th>Baseline</th><th>Candidate</th><th>Change</th></tr></thead><tbody>
                  {comparison.prediction_changes.map((item) => <tr key={item.case_id}><td>{item.case_id.slice(0, 8)}</td><td>{item.expected_verdict}</td><td>{item.baseline_verdict ?? "—"}</td><td>{item.candidate_verdict ?? "—"}</td><td>{item.classification}</td></tr>)}
                </tbody></table>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
