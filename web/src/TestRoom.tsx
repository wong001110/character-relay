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
import { CharacterPortrait } from "./CharacterPortrait";
import { CredentialModal } from "./CredentialModal";
import { useI18n } from "./i18n";
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

function eventTimeLabel(value: string | null | undefined, language: string): string {
  if (!value) return "—";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "—";
  return new Intl.DateTimeFormat(language === "zh-CN" ? "zh-CN" : "en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(timestamp);
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
  const [autoScroll, setAutoScroll] = useState(true);
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
  const replyCount = events.filter((item) => item.event_type === "subject_response").length;
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
  const setupReady =
    credentialReady &&
    selected.length > 0 &&
    (testerMode !== "adaptive" || adaptiveReady) &&
    (judgeMode === "rules" || semanticReady);
  const sessionLabel = run
    ? t(statusKeys[run.status])
    : credential === null && target.target_kind === "prompt_model"
      ? t("credential.checking")
      : setupReady
        ? t("room.ready")
        : t("room.configurationRequired");
  const sessionTone = run?.status === "failed"
    ? "danger"
    : run?.status === "running" || run?.status === "completed"
      ? "success"
      : setupReady
        ? "success"
        : "warning";
  const firstEventAt = events[0]?.created_at;

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
    if (!autoScroll) return;
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: mode === "watch" ? "smooth" : "auto"
    });
  }, [autoScroll, displayEvents, mode]);

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
          <Button variant="secondary" className="back-button" onClick={onBack}>
            {language === "zh-CN"
              ? `← 返回 ${card.display_name} / 角色档案`
              : `← Back to ${card.display_name} / Character File`}
          </Button>
          <div className="room-title-block">
            <h1>LIVE CHARACTER EXPERIMENT</h1>
            <p className="room-subject-line">{card.display_name} · {card.subtitle}</p>
          </div>
          <div className="room-header-actions">
            <div className="room-session-state">
              <StatusIndicator tone={sessionTone} pulse={busy}>{sessionLabel}</StatusIndicator>
              <small>
                {firstEventAt
                  ? `${language === "zh-CN" ? "开始" : "Started"} ${eventTimeLabel(firstEventAt, language)}`
                  : language === "zh-CN" ? "尚未开始" : "Not started"}
              </small>
            </div>
            <div className="room-session-id-note">
              <span>SESSION ID</span>
              <strong>{run?.id ?? "—"}</strong>
            </div>
          </div>
        </header>

        <section className="room-grid">
          <aside className="room-sidebar paper-sheet">
            <div className="room-setup-heading">
              <span>EXPERIMENT SETUP</span>
              <small className={setupReady ? "is-ready" : "needs-setup"}>{sessionLabel}</small>
            </div>
            <div className={`mini-card portrait-${card.portrait_variant}`}>
              <CharacterPortrait cardId={card.id} alt="" />
              <div>
                <span>{t(subjectKeys[card.subject_type])}</span>
                <strong>{card.display_name}</strong>
                <small>{card.subtitle}</small>
              </div>
            </div>

            {target.target_kind === "prompt_model" && (
              <details
                className={credentialReady ? "connection-card ready" : "connection-card missing"}
                open={!credentialReady}
              >
                <summary>
                  <span>{t("room.aiConnection")}</span>
                  <strong>{credentialCopy}</strong>
                </summary>
                <div className="connection-title">
                  <span>{t("room.provider")}</span><strong>{provider} · {model}</strong>
                </div>
                <dl>
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
              </details>
            )}

            <p className="section-label">{t("room.testerStyle")}</p>
            <div className="tester-mode-switch">
              <button
                className={testerMode === "benchmark" ? "selected" : ""}
                aria-pressed={testerMode === "benchmark"}
                onClick={() => setTesterMode("benchmark")}
                disabled={busy}
              >
                {t("room.benchmark")}<small>{t("room.benchmarkHelp")}</small>
              </button>
              <button
                className={testerMode === "adaptive" ? "selected" : ""}
                aria-pressed={testerMode === "adaptive"}
                onClick={() => setTesterMode("adaptive")}
                disabled={busy || !adaptiveReady}
              >
                {t("room.adaptive")}<small>{t("room.adaptiveHelp")}</small>
              </button>
            </div>

            <p className="section-label">{t("room.judgeMode")}</p>
            <div className="judge-mode-switch">
              {(["rules", "semantic", "hybrid"] as JudgeMode[]).map((item) => (
                <button
                  key={item}
                  className={judgeMode === item ? "selected" : ""}
                  aria-pressed={judgeMode === item}
                  onClick={() => setJudgeMode(item)}
                  disabled={busy || (item !== "rules" && !semanticReady)}
                >
                  {t(`judge.${item}` as "judge.rules")}
                  <small>{t(`judge.${item}Help` as "judge.rulesHelp")}</small>
                </button>
              ))}
            </div>

            <p className="section-label">{t("room.testLanguage")}</p>
            <p className="section-help">{t("room.testLanguageHelp")}</p>
            <div className="test-language-switch">
              <button
                className={testLanguage === "en" ? "selected" : ""}
                aria-pressed={testLanguage === "en"}
                onClick={() => setTestLanguage("en")}
                disabled={busy}
              >
                EN<small>{t("room.testEnglish")}</small>
              </button>
              <button
                className={testLanguage === "zh-CN" ? "selected" : ""}
                aria-pressed={testLanguage === "zh-CN"}
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
                  aria-pressed={selected.includes(suite.id)}
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
                aria-pressed={mode === "watch"}
                onClick={() => setMode("watch")}
                disabled={busy}
              >
                {t("room.watch")}<small>{t("room.watchHelp")}</small>
              </button>
              <button
                className={mode === "fast" ? "selected" : ""}
                aria-pressed={mode === "fast"}
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
                <StickyLabel variant="link" className="room-live-label">LIVE CONVERSATION</StickyLabel>
                <h2>{scenarioName}</h2>
              </div>
              <div className="room-chat-controls">
                <label className="room-auto-scroll">
                  <span>Auto-scroll</span>
                  <input
                    type="checkbox"
                    checked={autoScroll}
                    onChange={(event) => setAutoScroll(event.currentTarget.checked)}
                  />
                </label>
                <span className="round-counter">{t("room.replies", { count: replyCount })}</span>
              </div>
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
                  <div className="room-timeline-event" key={event.sequence}>
                    <time dateTime={event.created_at}>{eventTimeLabel(event.created_at, language)}</time>
                    <div className="room-timeline-content">
                      <LiveEvent event={event} card={card} />
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <aside className="observation-sidebar paper-sheet">
            <StickyLabel variant="image" className="room-observation-label">OBSERVATION BOARD</StickyLabel>
            <div className="room-observation-stats">
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
              <StickyNote variant="character" size="md" className="evidence-card">
                <span>{t("room.evidence")}</span>
                <strong>{eventCount}</strong>
                <small>{run ? t(statusKeys[run.status]) : t("room.unobserved")}</small>
              </StickyNote>
            </div>
            <div className="room-observation-board-grid">
              <section className="room-session-overview">
                <span>SESSION OVERVIEW</span>
                <dl className="signal-list">
                  <div><dt>{t("room.tester")}</dt><dd>{testerMode === "adaptive" ? t("room.adaptive") : t("room.benchmark")}</dd></div>
                  <div><dt>{t("room.judgeMode")}</dt><dd>{t(`judge.${judgeMode}` as "judge.rules")}</dd></div>
                  <div><dt>{language === "zh-CN" ? "测试语言" : "Language"}</dt><dd>{testLanguage === "zh-CN" ? "简体中文" : "English"}</dd></div>
                  <div><dt>{t("room.currentRoom")}</dt><dd>{scenarioName}</dd></div>
                  <div><dt>{language === "zh-CN" ? "回合" : "Turns"}</dt><dd>{replyCount}</dd></div>
                  <div><dt>{t("room.sessionState")}</dt><dd>{run ? t(statusKeys[run.status]) : t("room.unobserved")}</dd></div>
                </dl>
              </section>
              <StickyNote variant={breakpoint ? "warning" : "character"} size="sm" className="room-fracture-note">
                <span>{t("room.firstFracture")}</span>
                <strong>
                  {breakpoint
                    ? `${breakpoint.scenario.name} · ${t("event.turn", { turn: breakpoint.breakpoint ?? 0 })}`
                    : t("room.noneYet")}
                </strong>
                <small>{breakpoint ? t("judge.review") : language === "zh-CN" ? "继续观察…" : "Keep watching…"}</small>
              </StickyNote>
              <div className={comparison ? (comparison.gate_passed ? "comparison pass" : "comparison fail") : "comparison pending"}>
                <span>{language === "zh-CN" ? "对比" : "COMPARISON"}</span>
                {comparison ? (
                  <>
                    <Stamp variant={comparison.gate_passed ? "success" : "danger"}>
                      {comparison.gate_passed ? t("room.noRegression") : t("room.regression")}
                    </Stamp>
                    <small>{comparison.score_delta >= 0 ? "+" : ""}{comparison.score_delta.toFixed(1)} {t("room.scoreSuffix")}</small>
                  </>
                ) : (
                  <small>{language === "zh-CN" ? "尚无可比较的基准运行。" : "No comparable benchmark run yet."}</small>
                )}
              </div>
              <StickyNote variant="character" size="sm" className="card-profile-note">
                <span>{t("room.personaNote")}</span>
                <p>{card.persona_summary || t("room.noPersona")}</p>
              </StickyNote>
              <section className="room-session-actions">
                <span>{language === "zh-CN" ? "会话操作" : "SESSION ACTIONS"}</span>
                <Button
                  variant="secondary"
                  onClick={() => setReportFormat("markdown")}
                  disabled={run?.status !== "completed"}
                >
                  {t("room.labNote")}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setReportFormat("json")}
                  disabled={run?.status !== "completed"}
                >
                  {t("room.json")}
                </Button>
              </section>
            </div>
          </aside>
        </section>

        <footer className="room-readiness-strip" aria-label={language === "zh-CN" ? "实验运行状态" : "Experiment readiness"}>
          <div><span>{t("room.provider")}</span><strong>{provider}</strong></div>
          <div><span>{t("room.model")}</span><strong title={model}>{model}</strong></div>
          <div><span>{language === "zh-CN" ? "凭证" : "Credential"}</span><strong className={credentialReady ? "ready" : "missing"}>{credentialCopy}</strong></div>
          <div><span>{t("room.pressureAgent")}</span><strong className={adaptiveReady ? "ready" : "missing"}>{adaptiveReady ? `${runtime?.adaptive.provider} · ${runtime?.adaptive.model}` : t("room.configurationRequired")}</strong></div>
          <div><span>{t("room.semanticJudge")}</span><strong className={semanticReady ? "ready" : "missing"}>{semanticReady ? `${runtime?.judge.provider} · ${runtime?.judge.model}` : t("room.configurationRequired")}</strong></div>
          <Button variant="ghost" onClick={onAdmin}>{t("shelf.admin")}</Button>
        </footer>
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
          <CharacterPortrait cardId={card.id} alt="" />
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
          <CharacterPortrait cardId={card.id} alt="" />
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
