import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type CharacterCard,
  type ComparisonResult,
  type CredentialStatus,
  type JudgeMode,
  type ObservationMode,
  type ReportFormat,
  type RuntimeStatus,
  type TargetView,
  type TesterMode,
  type TestKind,
  type TestLanguage,
  type TrialEvent,
  type TrialRun
} from "./api";
import {
  Button,
  EmptyState,
  Stamp,
  StatusIndicator,
  StickyLabel,
  StickyNote,
  Toast
} from "./components/ui";
import { CredentialModal } from "./CredentialModal";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { latestScenarioName, payloadNumber, payloadText, visibleEvents } from "./live";
import { ReportModal } from "./ReportModal";
import { firstBreakpoint, integrityBand } from "./summary";
import "./adaptive.css";

interface Props {
  card: CharacterCard;
  target: TargetView;
  runtime: RuntimeStatus | null;
  onBack: () => void;
  onAdmin: () => void;
}

const suites = [
  { id: "identity_integrity", titleKey: "suite.identity", roomKey: "suite.mirrorRoom" },
  { id: "false_memory", titleKey: "suite.falseMemory", roomKey: "suite.memoryRoom" },
  { id: "prompt_injection", titleKey: "suite.intrusion", roomKey: "suite.scriptRoom" },
  { id: "long_conversation_drift", titleKey: "suite.longDrift", roomKey: "suite.echoHall" }
] as const satisfies ReadonlyArray<{
  id: TestKind;
  titleKey: string;
  roomKey: string;
}>;

const subjectKeys = {
  companion: "subject.companion",
  npc: "subject.npc",
  assistant: "subject.assistant",
  custom: "subject.custom"
} as const;

const integrityKeys = {
  intact: "integrity.intact",
  strained: "integrity.strained",
  fractured: "integrity.fractured",
  collapsed: "integrity.collapsed"
} as const;

const statusKeys = {
  pending: "status.pending",
  running: "status.running",
  completed: "status.completed",
  failed: "status.failed",
  cancelled: "status.cancelled"
} as const;

const severityKeys = {
  info: "severity.info",
  low: "severity.low",
  medium: "severity.medium",
  high: "severity.high",
  critical: "severity.critical"
} as const;

function evidenceCount(events: TrialEvent[]): number {
  return events.reduce((total, event) => {
    if (event.event_type !== "judge_result") return total;
    const value = event.payload.evidence;
    return total + (Array.isArray(value) ? value.length : 0);
  }, 0);
}

function configText(target: TargetView, key: string, fallback: string): string {
  const value = target.config[key];
  return typeof value === "string" && value ? value : fallback;
}

export function TestRoom({ card, target, runtime, onBack, onAdmin }: Props) {
  const { language, t } = useI18n();
  const [selected, setSelected] = useState<TestKind[]>(
    card.preferred_suites.length > 0 ? card.preferred_suites : suites.map((item) => item.id)
  );
  const [testLanguage, setTestLanguage] = useState<TestLanguage>(language);
  const [mode, setMode] = useState<ObservationMode>("watch");
  const [testerMode, setTesterMode] = useState<TesterMode>("benchmark");
  const [judgeMode, setJudgeMode] = useState<JudgeMode>(runtime?.default_judge_mode ?? "rules");
  const [events, setEvents] = useState<TrialEvent[]>([]);
  const [run, setRun] = useState<TrialRun | null>(null);
  const [benchmarkRuns, setBenchmarkRuns] = useState<Record<string, TrialRun>>({});
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [credential, setCredential] = useState<CredentialStatus | null>(null);
  const [showCredential, setShowCredential] = useState(false);
  const [reportFormat, setReportFormat] = useState<ReportFormat | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const displayEvents = useMemo(() => visibleEvents(events), [events]);
  const results = run?.result?.results ?? [];
  const breakpoint = firstBreakpoint(results);
  const score = run?.result?.average_score ?? 0;
  const rawScenarioName = latestScenarioName(events);
  const scenarioName = events.some((item) => item.event_type === "scenario_started")
    ? rawScenarioName
    : t("room.waitingRoom");
  const eventCount = evidenceCount(events);
  const credentialReady = credential?.configured ?? target.target_kind !== "prompt_model";
  const adaptiveReady = runtime?.adaptive.configured ?? false;
  const semanticReady = runtime?.judge.configured ?? false;
  const provider = configText(target, "provider", t("room.compatibleProvider"));
  const model = configText(target, "model", t("room.unspecifiedModel"));
  const baseUrl = configText(target, "base_url", t("room.noEndpoint"));
  const credentialCopy = !credential
    ? t("credential.checking")
    : !credential.required
      ? t("credential.notRequired")
      : !credential.configured
        ? t("credential.required")
        : credential.source === "environment"
          ? t("credential.environmentReady")
          : t("credential.sessionReady");

  useEffect(() => {
    if (runtime?.default_judge_mode && !busy) {
      const requested = runtime.default_judge_mode;
      setJudgeMode(
        requested === "rules" || semanticReady ? requested : "rules"
      );
    }
  }, [runtime?.default_judge_mode, semanticReady, busy]);

  useEffect(() => {
    let active = true;
    api.getCredentialStatus(card.id)
      .then((next) => { if (active) setCredential(next); })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [card.id]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: mode === "watch" ? "smooth" : "auto"
    });
  }, [displayEvents, mode]);

  function toggleSuite(id: TestKind) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  async function start() {
    if (!credentialReady) {
      setShowCredential(true);
      return;
    }
    if (testerMode === "adaptive" && !adaptiveReady) {
      setError(t("room.adminAdaptiveMissing"));
      return;
    }
    if (judgeMode !== "rules" && !semanticReady) {
      setError(t("room.adminJudgeMissing"));
      return;
    }

    setBusy(true);
    setError(null);
    setComparison(null);
    setEvents([]);
    const baselineKey = `${testLanguage}:${judgeMode}`;
    const baseline = testerMode === "benchmark" ? benchmarkRuns[baselineKey] ?? null : null;
    try {
      const created = await api.startTrial(
        card.id,
        selected,
        mode,
        testerMode,
        judgeMode,
        testLanguage
      );
      setRun(created);
      const completed = await api.observeTrial(created.id, mode, setEvents, setRun);
      setRun(completed);
      if (completed.status === "failed") {
        setError(completed.error ?? t("room.providerFailed"));
      }
      if (
        testerMode === "benchmark" &&
        completed.status === "completed" &&
        !completed.result?.review_required
      ) {
        if (baseline && baseline.id !== completed.id) {
          try {
            setComparison(await api.compareRuns(baseline.id, completed.id));
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : t("room.comparisonUnavailable"));
          }
        }
        setBenchmarkRuns((current) => ({ ...current, [baselineKey]: completed }));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("room.signalLost"));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!run || !["pending", "running"].includes(run.status)) return;
    try {
      setRun(await api.cancelTrial(run.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("room.stopFailed"));
    }
  }

  return (
    <>
      <main className="room-page">
        <header className="room-header">
          <Button variant="secondary" className="back-button" onClick={onBack}>{t("room.back")}</Button>
          <div><p className="kicker">{t("room.kicker")}</p><h1>{t("room.title")}</h1></div>
          <div className="room-header-actions">
            <LanguageSwitcher />
            <Button variant="secondary" onClick={onAdmin}>{t("shelf.admin")}</Button>
            <StatusIndicator tone={busy ? "info" : "neutral"} pulse={busy}>
              {busy ? t("room.sessionLive") : t("room.ready")}
            </StatusIndicator>
          </div>
        </header>

        <section className="room-grid">
          <aside className="room-sidebar paper-sheet">
            <div className={`mini-card portrait-${card.portrait_variant}`}>
              <img src="/assets/character-silhouette.svg" alt="" />
              <div>
                <span>{t(subjectKeys[card.subject_type])}</span>
                <strong>{card.display_name}</strong>
                <small>{card.subtitle}</small>
              </div>
            </div>

            {target.target_kind === "prompt_model" && (
              <div className={credentialReady ? "connection-card ready" : "connection-card missing"}>
                <div className="connection-title">
                  <span>{t("room.aiConnection")}</span><strong>{credentialCopy}</strong>
                </div>
                <dl>
                  <div><dt>{t("room.provider")}</dt><dd>{provider}</dd></div>
                  <div><dt>{t("room.model")}</dt><dd>{model}</dd></div>
                  <div><dt>{t("room.baseUrl")}</dt><dd title={baseUrl}>{baseUrl}</dd></div>
                </dl>
                <Button
                  variant="secondary"
                  className="full"
                  onClick={() => setShowCredential(true)}
                  disabled={busy}
                >
                  {credentialReady ? t("room.replaceKey") : t("room.configureKey")}
                </Button>
              </div>
            )}

            <p className="section-label">{t("room.testerStyle")}</p>
            <div className="tester-mode-switch">
              <button
                className={testerMode === "benchmark" ? "selected" : ""}
                onClick={() => setTesterMode("benchmark")}
                disabled={busy}
              >
                {t("room.benchmark")}<small>{t("room.benchmarkHelp")}</small>
              </button>
              <button
                className={testerMode === "adaptive" ? "selected" : ""}
                onClick={() => setTesterMode("adaptive")}
                disabled={busy || !adaptiveReady}
              >
                {t("room.adaptive")}<small>{t("room.adaptiveHelp")}</small>
              </button>
            </div>
            <RuntimeSummary
              title={t("room.pressureAgent")}
              configured={adaptiveReady}
              provider={runtime?.adaptive.provider ?? "—"}
              model={runtime?.adaptive.model ?? "—"}
              onAdmin={onAdmin}
            />

            <p className="section-label">{t("room.judgeMode")}</p>
            <div className="judge-mode-switch">
              {(["rules", "semantic", "hybrid"] as JudgeMode[]).map((item) => (
                <button
                  key={item}
                  className={judgeMode === item ? "selected" : ""}
                  onClick={() => setJudgeMode(item)}
                  disabled={busy || (item !== "rules" && !semanticReady)}
                >
                  {t(`judge.${item}` as "judge.rules")}
                  <small>{t(`judge.${item}Help` as "judge.rulesHelp")}</small>
                </button>
              ))}
            </div>
            <RuntimeSummary
              title={t("room.semanticJudge")}
              configured={semanticReady}
              provider={runtime?.judge.provider ?? "—"}
              model={runtime?.judge.model ?? "—"}
              onAdmin={onAdmin}
            />

            <p className="section-label">{t("room.testLanguage")}</p>
            <p className="section-help">{t("room.testLanguageHelp")}</p>
            <div className="test-language-switch">
              <button
                className={testLanguage === "en" ? "selected" : ""}
                onClick={() => setTestLanguage("en")}
                disabled={busy}
              >
                EN<small>{t("room.testEnglish")}</small>
              </button>
              <button
                className={testLanguage === "zh-CN" ? "selected" : ""}
                onClick={() => setTestLanguage("zh-CN")}
                disabled={busy}
              >
                简<small>{t("room.testChinese")}</small>
              </button>
            </div>

            <p className="section-label">{t("room.chooseRooms")}</p>
            <div className="room-list">
              {suites.map((suite) => (
                <button
                  key={suite.id}
                  className={selected.includes(suite.id) ? "room-choice selected" : "room-choice"}
                  onClick={() => toggleSuite(suite.id)}
                  disabled={busy}
                >
                  <span>{t(suite.roomKey)}</span><small>{t(suite.titleKey)}</small>
                </button>
              ))}
            </div>

            <p className="section-label">{t("room.observationSpeed")}</p>
            <div className="mode-switch">
              <button
                className={mode === "watch" ? "selected" : ""}
                onClick={() => setMode("watch")}
                disabled={busy}
              >
                {t("room.watch")}<small>{t("room.watchHelp")}</small>
              </button>
              <button
                className={mode === "fast" ? "selected" : ""}
                onClick={() => setMode("fast")}
                disabled={busy}
              >
                {t("room.fast")}<small>{t("room.fastHelp")}</small>
              </button>
            </div>

            <Button
              variant="primary"
              className="full room-begin-button"
              onClick={() => void start()}
              disabled={busy || selected.length === 0}
            >
              {busy
                ? t("room.observing")
                : !credentialReady
                  ? t("room.configureSubject")
                  : t("room.begin")}
            </Button>
            {busy && (
              <Button variant="secondary" className="full" onClick={() => void stop()}>
                {t("room.stop")}
              </Button>
            )}
            {error && <Toast tone="danger" className="room-error-toast">{error}</Toast>}
          </aside>

          <section className="chat-sheet paper-sheet">
            <div className="chat-heading">
              <div>
                <StickyLabel variant="link" className="room-live-label">{t("room.liveRoom")}</StickyLabel>
                <h2>{scenarioName}</h2>
              </div>
              <span className="round-counter">
                {t("room.replies", {
                  count: events.filter((item) => item.event_type === "subject_response").length
                })}
              </span>
            </div>
            <div className="chatroom" ref={transcriptRef} aria-live="polite">
              {displayEvents.length === 0 ? (
                <EmptyState
                  className="room-empty"
                  illustration={<img src="/assets/masque-mark.svg" alt="" />}
                  title={t("room.quiet")}
                  description={t("room.quietHelp")}
                />
              ) : (
                displayEvents.map((event) => (
                  <LiveEvent key={event.sequence} event={event} card={card} />
                ))
              )}
            </div>
          </section>

          <aside className="observation-sidebar paper-sheet">
            <StickyLabel variant="image" className="room-observation-label">{t("room.notes")}</StickyLabel>
            <StickyNote
              variant={run?.result?.review_required ? "warning" : "note"}
              size="md"
              className={run?.result?.review_required ? "integrity-card review" : "integrity-card"}
            >
              <span>{t("room.integrity")}</span><strong>{run?.result ? Math.round(score) : "—"}</strong>
              <small>
                {run?.result?.review_required
                  ? t("judge.review")
                  : run?.result
                    ? t(integrityKeys[integrityBand(score)])
                    : t("room.stillObserving")}
              </small>
            </StickyNote>
            <dl className="signal-list">
              <div><dt>{t("room.tester")}</dt><dd>{testerMode === "adaptive" ? t("room.adaptive") : t("room.benchmark")}</dd></div>
              <div><dt>{t("room.judgeMode")}</dt><dd>{t(`judge.${judgeMode}` as "judge.rules")}</dd></div>
              <div><dt>{t("room.currentRoom")}</dt><dd>{scenarioName}</dd></div>
              <div><dt>{t("room.evidence")}</dt><dd>{eventCount}</dd></div>
              <div>
                <dt>{t("room.firstFracture")}</dt>
                <dd>
                  {breakpoint
                    ? `${breakpoint.scenario.name} · ${t("event.turn", { turn: breakpoint.breakpoint ?? 0 })}`
                    : t("room.noneYet")}
                </dd>
              </div>
              <div><dt>{t("room.sessionState")}</dt><dd>{run ? t(statusKeys[run.status]) : t("room.unobserved")}</dd></div>
            </dl>
            {comparison && (
              <div className={comparison.gate_passed ? "comparison pass" : "comparison fail"}>
                <span>{t("room.compared")}</span>
                <Stamp variant={comparison.gate_passed ? "success" : "danger"}>
                  {comparison.gate_passed ? t("room.noRegression") : t("room.regression")}
                </Stamp>
                <small>{comparison.score_delta >= 0 ? "+" : ""}{comparison.score_delta.toFixed(1)} {t("room.scoreSuffix")}</small>
              </div>
            )}
            <StickyNote variant="character" size="sm" className="card-profile-note">
              <span>{t("room.personaNote")}</span>
              <p>{card.persona_summary || t("room.noPersona")}</p>
            </StickyNote>
            {run?.status === "completed" && (
              <div className="report-links">
                <Button variant="secondary" onClick={() => setReportFormat("markdown")}>{t("room.labNote")}</Button>
                <Button variant="ghost" onClick={() => setReportFormat("json")}>{t("room.json")}</Button>
              </div>
            )}
          </aside>
        </section>
      </main>

      {showCredential && (
        <CredentialModal
          card={card}
          target={target}
          onClose={() => setShowCredential(false)}
          onConfigured={setCredential}
        />
      )}
      {reportFormat && run && (
        <ReportModal
          runId={run.id}
          format={reportFormat}
          onClose={() => setReportFormat(null)}
        />
      )}
    </>
  );
}

function RuntimeSummary({
  title,
  configured,
  provider,
  model,
  onAdmin
}: {
  title: string;
  configured: boolean;
  provider: string;
  model: string;
  onAdmin: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className={configured ? "adaptive-summary" : "adaptive-summary missing"}>
      <span>{title}</span>
      <strong>{configured ? `${provider} · ${model}` : t("room.configurationRequired")}</strong>
      <small>{configured ? t("room.adminManaged") : t("room.adminRuntimeMissing")}</small>
      <Button variant="secondary" className="full" onClick={onAdmin}>{t("room.openAdmin")}</Button>
    </div>
  );
}

function LiveEvent({ event, card }: { event: TrialEvent; card: CharacterCard }) {
  const { t } = useI18n();

  if (event.event_type === "scenario_started") {
    return (
      <div className="system-note">
        <span>{t("event.roomOpened")}</span>
        <strong>{payloadText(event, "name")}</strong>
        <small>{payloadText(event, "expected_behavior")}</small>
      </div>
    );
  }
  if (event.event_type === "tester_thinking") {
    return (
      <div className="chat-line tester-line">
        <div className="chat-avatar tester-avatar">T</div>
        <div className="bubble tester-thinking-bubble">
          <span>{t("event.adaptivePlanning")}</span><p><i /><i /><i /></p>
        </div>
      </div>
    );
  }
  if (event.event_type === "tester_message") {
    const source = payloadText(event, "source");
    return (
      <div className="chat-line tester-line">
        <div className="chat-avatar tester-avatar">T</div>
        <div className="bubble tester-bubble">
          <span>
            {source === "adaptive" ? t("event.adaptiveTester") : t("event.benchmarkTester")}
            {` · ${t("event.turn", { turn: event.turn_index ?? 0 })}`}
          </span>
          <p>{payloadText(event, "message")}</p>
        </div>
      </div>
    );
  }
  if (event.event_type === "subject_typing") {
    return (
      <div className="chat-line subject-line">
        <div className="bubble subject-bubble typing-bubble">
          <span>{card.display_name}</span><p><i /><i /><i /></p>
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
          <span>{card.display_name}{latency !== null ? ` · ${latency} ms` : ""}</span>
          <p>{payloadText(event, "message")}</p>
        </div>
        <div className={`chat-avatar subject-avatar portrait-${card.portrait_variant}`}>
          <img src="/assets/character-silhouette.svg" alt="" />
        </div>
      </div>
    );
  }
  if (event.event_type === "judge_thinking") {
    return (
      <div className="judge-note thinking">
        <span>{t("event.semanticJudging")}</span>
        <strong>{payloadText(event, "model")}</strong>
        <p><i /><i /><i /></p>
      </div>
    );
  }
  if (event.event_type === "judge_result") {
    const passed = event.payload.passed === true;
    const review = event.payload.review_required === true;
    return (
      <div className={review ? "judge-note review" : passed ? "judge-note pass" : "judge-note fail"}>
        <span>{t("event.judgeMemo")} · {payloadText(event, "judge_mode")}</span>
        <Stamp variant={review || !passed ? "danger" : "success"}>
          {review ? t("judge.review") : passed ? t("event.roleHeld") : t("event.driftObserved")}
        </Stamp>
        <p>{payloadText(event, "summary")}</p>
        <small>
          {t("event.score", { score: payloadNumber(event, "score") ?? 0 })}
          {payloadNumber(event, "semantic_score") !== null
            ? ` · R ${payloadNumber(event, "rule_score")} / S ${payloadNumber(event, "semantic_score")}`
            : ""}
        </small>
      </div>
    );
  }
  if (event.event_type === "breakpoint_detected") {
    const rawSeverity = payloadText(event, "severity");
    const severity = rawSeverity in severityKeys
      ? t(severityKeys[rawSeverity as keyof typeof severityKeys])
      : rawSeverity;
    return (
      <div className="fracture-banner">
        <img src="/assets/fracture-stamp.svg" alt="" />
        <div>
          <span>{t("event.breakpoint")}</span>
          <strong>{t("event.turnNumber", { turn: event.turn_index ?? 0 })}</strong>
          <small>{t("event.severity", { severity })}</small>
        </div>
      </div>
    );
  }
  if (event.event_type === "session_completed") {
    return (
      <div className="system-note completed">
        <span>{event.payload.review_required === true ? t("judge.review") : t("event.complete")}</span>
        <strong>{t("event.averageScore", { score: payloadNumber(event, "average_score") ?? 0 })}</strong>
      </div>
    );
  }
  if (event.event_type === "session_failed") {
    return <div className="system-note failed">{payloadText(event, "message")}</div>;
  }
  return null;
}
