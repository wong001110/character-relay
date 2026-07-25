import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type CharacterCard,
  type ComparisonResult,
  type ObservationMode,
  type TestKind,
  type TrialEvent,
  type TrialRun
} from "./api";
import {
  latestScenarioName,
  payloadNumber,
  payloadText,
  visibleEvents
} from "./live";
import { firstBreakpoint, integrityLabel } from "./summary";

interface Props {
  card: CharacterCard;
  onBack: () => void;
}

const suites: Array<{ id: TestKind; title: string; room: string }> = [
  { id: "identity_integrity", title: "Identity", room: "Mirror Room" },
  { id: "false_memory", title: "False memory", room: "Memory Room" },
  { id: "prompt_injection", title: "Intrusion", room: "Script Room" },
  { id: "long_conversation_drift", title: "Long drift", room: "Echo Hall" }
];

function evidenceCount(events: TrialEvent[]): number {
  return events.reduce((total, event) => {
    if (event.event_type !== "judge_result") return total;
    const value = event.payload.evidence;
    return total + (Array.isArray(value) ? value.length : 0);
  }, 0);
}

export function TestRoom({ card, onBack }: Props) {
  const [selected, setSelected] = useState<TestKind[]>(
    card.preferred_suites.length > 0
      ? card.preferred_suites
      : suites.map((item) => item.id)
  );
  const [mode, setMode] = useState<ObservationMode>("watch");
  const [events, setEvents] = useState<TrialEvent[]>([]);
  const [run, setRun] = useState<TrialRun | null>(null);
  const [previousRun, setPreviousRun] = useState<TrialRun | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const displayEvents = useMemo(() => visibleEvents(events), [events]);
  const results = run?.result?.results ?? [];
  const breakpoint = firstBreakpoint(results);
  const score = run?.result?.average_score ?? 0;
  const scenarioName = latestScenarioName(events);
  const eventCount = evidenceCount(events);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: mode === "watch" ? "smooth" : "auto"
    });
  }, [displayEvents, mode]);

  function toggleSuite(id: TestKind) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id]
    );
  }

  async function start() {
    setBusy(true);
    setError(null);
    setComparison(null);
    setEvents([]);
    const baseline = run?.status === "completed" ? run : previousRun;
    if (run?.status === "completed") setPreviousRun(run);
    try {
      const created = await api.startTrial(card.id, selected, mode);
      setRun(created);
      const completed = await api.observeTrial(created.id, setEvents, setRun);
      setRun(completed);
      if (baseline && baseline.id !== completed.id) {
        setComparison(await api.compareRuns(baseline.id, completed.id));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The room lost its signal.");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!run || !["pending", "running"].includes(run.status)) return;
    try {
      setRun(await api.cancelTrial(run.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not stop the session.");
    }
  }

  return (
    <main className="room-page">
      <header className="room-header">
        <button className="back-button" onClick={onBack}>
          ← Character Shelf
        </button>
        <div>
          <p className="kicker">Live character observation</p>
          <h1>Test Room</h1>
        </div>
        <div className={`live-light ${busy ? "active" : ""}`}>
          <span />
          {busy ? "Session live" : "Room ready"}
        </div>
      </header>

      <section className="room-grid">
        <aside className="room-sidebar paper-sheet">
          <div className={`mini-card portrait-${card.portrait_variant}`}>
            <img src="/assets/character-silhouette.svg" alt="" />
            <div>
              <span>{card.subject_type}</span>
              <strong>{card.display_name}</strong>
              <small>{card.subtitle}</small>
            </div>
          </div>

          <p className="section-label">Choose rooms</p>
          <div className="room-list">
            {suites.map((suite) => (
              <button
                key={suite.id}
                className={selected.includes(suite.id) ? "room-choice selected" : "room-choice"}
                onClick={() => toggleSuite(suite.id)}
                disabled={busy}
              >
                <span>{suite.room}</span>
                <small>{suite.title}</small>
              </button>
            ))}
          </div>

          <p className="section-label">Observation speed</p>
          <div className="mode-switch">
            <button
              className={mode === "watch" ? "selected" : ""}
              onClick={() => setMode("watch")}
              disabled={busy}
            >
              Watch
              <small>paced chat</small>
            </button>
            <button
              className={mode === "fast" ? "selected" : ""}
              onClick={() => setMode("fast")}
              disabled={busy}
            >
              Fast
              <small>developer run</small>
            </button>
          </div>

          <button
            className="ink-button full"
            onClick={start}
            disabled={busy || selected.length === 0}
          >
            {busy ? "Observing…" : "Begin session"}
          </button>
          {busy && (
            <button className="paper-button full" onClick={stop}>
              Stop session
            </button>
          )}
          {error && <p className="error-note">{error}</p>}
        </aside>

        <section className="chat-sheet paper-sheet">
          <div className="chat-heading">
            <div>
              <p className="tape-label">Live Room</p>
              <h2>{scenarioName}</h2>
            </div>
            <span className="round-counter">
              {events.filter((item) => item.event_type === "subject_response").length} replies
            </span>
          </div>

          <div className="chatroom" ref={transcriptRef} aria-live="polite">
            {displayEvents.length === 0 ? (
              <div className="room-empty">
                <img src="/assets/masque-mark.svg" alt="" />
                <h3>The room is quiet.</h3>
                <p>Choose a room and begin the observation session.</p>
              </div>
            ) : (
              displayEvents.map((event) => (
                <LiveEvent key={event.sequence} event={event} card={card} />
              ))
            )}
          </div>
        </section>

        <aside className="observation-sidebar paper-sheet">
          <p className="tape-label rose">Observation Notes</p>
          <div className="integrity-card">
            <span>Masque integrity</span>
            <strong>{run?.result ? Math.round(score) : "—"}</strong>
            <small>{run?.result ? integrityLabel(score) : "Still observing"}</small>
          </div>

          <dl className="signal-list">
            <div>
              <dt>Current room</dt>
              <dd>{scenarioName}</dd>
            </div>
            <div>
              <dt>Evidence found</dt>
              <dd>{eventCount}</dd>
            </div>
            <div>
              <dt>First fracture</dt>
              <dd>
                {breakpoint
                  ? `${breakpoint.scenario.name} · turn ${breakpoint.breakpoint}`
                  : "None yet"}
              </dd>
            </div>
            <div>
              <dt>Session state</dt>
              <dd>{run?.status ?? "unobserved"}</dd>
            </div>
          </dl>

          {comparison && (
            <div className={comparison.gate_passed ? "comparison pass" : "comparison fail"}>
              <span>Compared with last run</span>
              <strong>{comparison.gate_passed ? "No regression" : "Regression"}</strong>
              <small>
                {comparison.score_delta >= 0 ? "+" : ""}
                {comparison.score_delta.toFixed(1)} score
              </small>
            </div>
          )}

          <div className="card-profile-note">
            <span>Persona note</span>
            <p>{card.persona_summary || "No persona note filed."}</p>
          </div>

          {run?.status === "completed" && (
            <div className="report-links">
              <a href={api.reportUrl(run.id, "markdown")}>Lab note</a>
              <a href={api.reportUrl(run.id, "json")}>JSON</a>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}

function LiveEvent({ event, card }: { event: TrialEvent; card: CharacterCard }) {
  if (event.event_type === "scenario_started") {
    return (
      <div className="system-note">
        <span>Room opened</span>
        <strong>{payloadText(event, "name")}</strong>
        <small>{payloadText(event, "expected_behavior")}</small>
      </div>
    );
  }

  if (event.event_type === "tester_message") {
    return (
      <div className="chat-line tester-line">
        <div className="chat-avatar tester-avatar">T</div>
        <div className="bubble tester-bubble">
          <span>Tester · turn {event.turn_index}</span>
          <p>{payloadText(event, "message")}</p>
        </div>
      </div>
    );
  }

  if (event.event_type === "subject_typing") {
    return (
      <div className="chat-line subject-line">
        <div className="bubble subject-bubble typing-bubble">
          <span>{card.display_name}</span>
          <p><i /><i /><i /></p>
        </div>
        <div className={`chat-avatar subject-avatar portrait-${card.portrait_variant}`}>
          <img src="/assets/character-silhouette.svg" alt="" />
        </div>
      </div>
    );
  }

  if (event.event_type === "subject_response") {
    const latency = payloadNumber(event, "latency_ms");
    return (
      <div className="chat-line subject-line">
        <div className="bubble subject-bubble">
          <span>
            {card.display_name}
            {latency !== null ? ` · ${latency} ms` : ""}
          </span>
          <p>{payloadText(event, "message")}</p>
        </div>
        <div className={`chat-avatar subject-avatar portrait-${card.portrait_variant}`}>
          <img src="/assets/character-silhouette.svg" alt="" />
        </div>
      </div>
    );
  }

  if (event.event_type === "judge_result") {
    const passed = event.payload.passed === true;
    return (
      <div className={passed ? "judge-note pass" : "judge-note fail"}>
        <span>Judge memo</span>
        <strong>{passed ? "Role held" : "Drift observed"}</strong>
        <p>{payloadText(event, "summary")}</p>
        <small>Score {payloadNumber(event, "score") ?? 0}</small>
      </div>
    );
  }

  if (event.event_type === "breakpoint_detected") {
    return (
      <div className="fracture-banner">
        <img src="/assets/fracture-stamp.svg" alt="" />
        <div>
          <span>Breakpoint detected</span>
          <strong>Turn {event.turn_index}</strong>
          <small>{payloadText(event, "severity")} severity</small>
        </div>
      </div>
    );
  }

  if (event.event_type === "session_completed") {
    return (
      <div className="system-note completed">
        <span>Observation complete</span>
        <strong>Average score {payloadNumber(event, "average_score") ?? 0}</strong>
      </div>
    );
  }

  if (event.event_type === "session_failed") {
    return <div className="system-note failed">{payloadText(event, "message")}</div>;
  }

  return null;
}
