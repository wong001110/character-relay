import { useEffect, useMemo, useState } from "react";
import { api, type TargetView, type TestKind, type TrialRun } from "./api";
import { firstBreakpoint, integrityLabel } from "./summary";
import "./styles.css";

const suites: Array<{ id: TestKind; title: string; note: string }> = [
  { id: "identity_integrity", title: "Identity", note: "Can the subject remain itself?" },
  { id: "false_memory", title: "False memory", note: "Will it accept an event that never happened?" },
  { id: "prompt_injection", title: "Intrusion", note: "Can hidden rules be displaced or exposed?" },
  { id: "long_conversation_drift", title: "Long drift", note: "What survives after repeated ordinary turns?" }
];

export default function App() {
  const [targets, setTargets] = useState<TargetView[]>([]);
  const [targetId, setTargetId] = useState("demo-fragile");
  const [selected, setSelected] = useState<TestKind[]>(suites.map((item) => item.id));
  const [run, setRun] = useState<TrialRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  useEffect(() => {
    api.listTargets().then(setTargets).catch((reason: Error) => setError(reason.message));
  }, []);

  const results = run?.result?.results ?? [];
  const breakpoint = useMemo(() => firstBreakpoint(results), [results]);
  const focused = results.find((item) => item.scenario.id === activeScenario) ?? breakpoint ?? results[0];
  const score = run?.result?.average_score ?? 0;

  async function start() {
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      const created = await api.startTrial(targetId, selected);
      const completed = await api.waitForTrial(created.id);
      setRun(completed);
      setActiveScenario(completed.result?.results[0]?.scenario.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unknown trial error");
    } finally {
      setBusy(false);
    }
  }

  function toggleSuite(id: TestKind) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <div className="brand-mark" aria-hidden="true"><span /></div>
        <div>
          <p className="eyebrow">Character observation chamber</p>
          <h1>Echo Masque</h1>
          <p className="subtitle">See what remains when the role is challenged.</p>
        </div>
        <div className="status-seal">MVP / local</div>
      </header>

      <section className="control-panel paper-panel">
        <div>
          <label htmlFor="target">Subject</label>
          <select id="target" value={targetId} onChange={(event: { currentTarget: { value: string } }) => setTargetId(event.currentTarget.value)}>
            {targets.map((target) => <option key={target.id} value={target.id}>{target.name}</option>)}
          </select>
        </div>
        <div className="suite-grid">
          {suites.map((suite) => (
            <button
              className={selected.includes(suite.id) ? "suite selected" : "suite"}
              key={suite.id}
              type="button"
              onClick={() => toggleSuite(suite.id)}
            >
              <span>{suite.title}</span><small>{suite.note}</small>
            </button>
          ))}
        </div>
        <button className="run-button" disabled={busy || selected.length === 0} onClick={start}>
          {busy ? "Observing…" : "Begin session"}
        </button>
        {error && <p className="error-note">{error}</p>}
      </section>

      <section className="observation-grid">
        <aside className="paper-panel results-rail">
          <p className="eyebrow">Masque integrity</p>
          <div className="score-ring"><strong>{Math.round(score)}</strong><span>/ 100</span></div>
          <h2>{run?.result ? integrityLabel(score) : "Unobserved"}</h2>
          <p>{breakpoint ? `First fracture: ${breakpoint.scenario.name}, turn ${breakpoint.breakpoint}` : run?.result ? "No breakpoint detected." : "Run a session to expose behavior signals."}</p>
          <div className="result-list">
            {results.map((item) => (
              <button key={item.scenario.id} onClick={() => setActiveScenario(item.scenario.id)} className={focused?.scenario.id === item.scenario.id ? "result active" : "result"}>
                <span>{item.scenario.name}</span><b>{item.verdict.score}</b>
              </button>
            ))}
          </div>
        </aside>

        <article className="paper-panel transcript-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Session replay</p><h2>{focused?.scenario.name ?? "No session selected"}</h2></div>
            {focused && <span className={focused.verdict.passed ? "verdict pass" : "verdict fail"}>{focused.verdict.passed ? "Pass" : "Breakpoint"}</span>}
          </div>
          {focused ? (
            <>
              <p className="expected">Expected: {focused.scenario.expected_behavior}</p>
              <div className="transcript">
                {focused.turns.map((turn) => (
                  <div className="turn" key={turn.index}>
                    <div className="tester"><span>Tester · {turn.index}</span><p>{turn.tester_message}</p></div>
                    <div className="subject"><span>Subject</span><p>{turn.target_response}</p></div>
                  </div>
                ))}
              </div>
              <div className="evidence-stack">
                {focused.verdict.evidence.map((item) => (
                  <div className="evidence" key={`${item.code}-${item.turn_index}`}>
                    <b>{item.code.replaceAll("_", " ")}</b><span>Turn {item.turn_index} · {item.severity}</span><p>{item.message}</p>
                  </div>
                ))}
              </div>
            </>
          ) : <div className="empty-state"><div className="empty-mask" /><p>The room is quiet. Select a subject and begin.</p></div>}
        </article>
      </section>
    </main>
  );
}
