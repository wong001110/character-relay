import { useEffect, useState } from "react";

import {
  api,
  type CharacterCard,
  type JudgeMode,
  type ObservationMode,
  type TesterMode,
  type TestLanguage,
  type TrialRun
} from "./api";
import { useI18n } from "./i18n";
import { ReportModal } from "./ReportModal";
import { workspaceApi, type TestPackView } from "./workspaceApi";

interface Props {
  cards: CharacterCard[];
}

export function PackRunLauncher({ cards }: Props) {
  const { language } = useI18n();
  const chinese = language === "zh-CN";
  const [packs, setPacks] = useState<TestPackView[]>([]);
  const [open, setOpen] = useState(false);
  const [cardId, setCardId] = useState("");
  const [packId, setPackId] = useState("");
  const [testLanguage, setTestLanguage] = useState<TestLanguage>(language);
  const [testerMode, setTesterMode] = useState<TesterMode>("benchmark");
  const [judgeMode, setJudgeMode] = useState<JudgeMode>("rules");
  const [mode, setMode] = useState<ObservationMode>("fast");
  const [run, setRun] = useState<TrialRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reportRunId, setReportRunId] = useState<string | null>(null);

  useEffect(() => {
    workspaceApi.listPacks()
      .then((items) => {
        setPacks(items);
        setPackId((current) => current || items[0]?.id || "");
      })
      .catch((reason: Error) => setMessage(reason.message));
  }, []);

  useEffect(() => {
    setCardId((current) => current || cards[0]?.id || "");
  }, [cards]);

  async function start() {
    const card = cards.find((item) => item.id === cardId);
    if (!card || !packId) {
      setMessage(chinese ? "请选择角色和测试包。" : "Select a Character Card and Test Pack.");
      return;
    }
    try {
      setBusy(true);
      setMessage(null);
      setRun(null);
      const created = await workspaceApi.startPackTrial(
        card,
        packId,
        mode,
        testerMode,
        judgeMode,
        testLanguage
      );
      setRun(created);
      const completed = await api.observeTrial(
        created.id,
        mode,
        () => undefined,
        setRun
      );
      setRun(completed);
      if (completed.status === "completed") {
        setMessage(chinese ? "测试包运行完成。" : "Test Pack run completed.");
      } else {
        setMessage(completed.error ?? (chinese ? "运行失败。" : "Run failed."));
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : (chinese ? "运行失败。" : "Run failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="pack-run-fab" onClick={() => setOpen((value) => !value)}>
        {chinese ? "运行测试包" : "Run Test Pack"}
      </button>
      {open && (
        <aside className="pack-run-launcher paper-sheet">
          <div className="pack-run-heading">
            <div>
              <span>{chinese ? "快速实验" : "Quick experiment"}</span>
              <h3>{chinese ? "运行测试包" : "Run a Test Pack"}</h3>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>
          <label>
            {chinese ? "角色" : "Character"}
            <select value={cardId} onChange={(event) => setCardId(event.currentTarget.value)}>
              <option value="">—</option>
              {cards.map((card) => (
                <option value={card.id} key={card.id}>{card.display_name}</option>
              ))}
            </select>
          </label>
          <label>
            {chinese ? "测试包" : "Test Pack"}
            <select value={packId} onChange={(event) => setPackId(event.currentTarget.value)}>
              <option value="">—</option>
              {packs.map((pack) => (
                <option value={pack.id} key={pack.id}>
                  {pack.name} · v{pack.version}
                </option>
              ))}
            </select>
          </label>
          <div className="pack-run-grid">
            <label>
              {chinese ? "语言" : "Language"}
              <select
                value={testLanguage}
                onChange={(event) => setTestLanguage(event.currentTarget.value as TestLanguage)}
              >
                <option value="en">English</option>
                <option value="zh-CN">简体中文</option>
              </select>
            </label>
            <label>
              Tester
              <select
                value={testerMode}
                onChange={(event) => setTesterMode(event.currentTarget.value as TesterMode)}
              >
                <option value="benchmark">Benchmark</option>
                <option value="adaptive">Adaptive</option>
              </select>
            </label>
            <label>
              Judge
              <select
                value={judgeMode}
                onChange={(event) => setJudgeMode(event.currentTarget.value as JudgeMode)}
              >
                <option value="rules">Rules</option>
                <option value="semantic">Semantic</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            <label>
              {chinese ? "速度" : "Speed"}
              <select
                value={mode}
                onChange={(event) => setMode(event.currentTarget.value as ObservationMode)}
              >
                <option value="fast">Fast</option>
                <option value="watch">Watch</option>
              </select>
            </label>
          </div>
          <button
            className="ink-button full"
            onClick={() => void start()}
            disabled={busy || cards.length === 0 || packs.length === 0}
          >
            {busy ? (chinese ? "运行中…" : "Running…") : (chinese ? "开始运行" : "Start run")}
          </button>
          {run && (
            <div className="pack-run-status">
              <span>{run.status}</span>
              <strong>{run.result ? `${run.result.average_score.toFixed(1)} / 100` : "—"}</strong>
              {run.status === "completed" && (
                <button onClick={() => setReportRunId(run.id)}>
                  {chinese ? "打开报告" : "Open report"}
                </button>
              )}
            </div>
          )}
          {message && <p className="error-note">{message}</p>}
          {packs.length === 0 && (
            <p className="section-help">
              {chinese ? "请先在测试包标签创建测试包。" : "Create a Test Pack in the Test Packs tab first."}
            </p>
          )}
        </aside>
      )}
      {reportRunId && (
        <ReportModal
          runId={reportRunId}
          format="markdown"
          onClose={() => setReportRunId(null)}
        />
      )}
    </>
  );
}
