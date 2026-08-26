import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  Button,
  EmptyState,
  FormField,
  Input,
  Select,
  Spinner,
  StatusIndicator,
  StickyLabel,
  Textarea,
  Toast
} from "./components/ui";
import {
  knowledgeFabricApi,
  type KnowledgeFabricCorpus,
  type KnowledgeFabricOperationalSource
} from "./knowledgeFabricApi";

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function KnowledgeFabricAdministrationPanel() {
  const [corpora, setCorpora] = useState<KnowledgeFabricCorpus[]>([]);
  const [sources, setSources] = useState<KnowledgeFabricOperationalSource[]>([]);
  const [selectedCorpusId, setSelectedCorpusId] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [corpusName, setCorpusName] = useState("");
  const [corpusDescription, setCorpusDescription] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [sourceLocator, setSourceLocator] = useState("");
  const [scheduleSourceId, setScheduleSourceId] = useState("");
  const [scheduleEnabled, setScheduleEnabled] = useState("false");
  const [scheduleInterval, setScheduleInterval] = useState("900");
  const requestVersion = useRef(0);
  const sourceRequestVersion = useRef(0);

  const selectedCorpus = corpora.find((corpus) => corpus.id === selectedCorpusId) ?? null;

  async function load() {
    const version = ++requestVersion.current;
    setLoading(true);
    try {
      const nextCorpora = await knowledgeFabricApi.listGlobalCorpora();
      if (version !== requestVersion.current) return;
      setCorpora(nextCorpora);
      setSelectedCorpusId((current) =>
        nextCorpora.some((corpus) => corpus.id === current)
          ? current
          : nextCorpora[0]?.id ?? ""
      );
      setError(null);
    } catch (reason) {
      if (version === requestVersion.current) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function setScheduleFields(source: KnowledgeFabricOperationalSource | undefined) {
    setScheduleEnabled(source?.external_schedule?.enabled ? "true" : "false");
    setScheduleInterval(String(source?.external_schedule?.interval_seconds ?? 900));
  }

  async function refreshSources(corpusId: string): Promise<void> {
    const version = ++sourceRequestVersion.current;
    const nextSources = await knowledgeFabricApi.listGlobalOperationalSources(corpusId);
    if (version !== sourceRequestVersion.current) return;
    setSources(nextSources);
    const nextSource = nextSources.find((source) => source.id === scheduleSourceId) ?? nextSources[0];
    setScheduleSourceId(nextSource?.id ?? "");
    setScheduleFields(nextSource);
  }

  useEffect(() => {
    if (!selectedCorpusId) {
      sourceRequestVersion.current += 1;
      setSources([]);
      setScheduleSourceId("");
      setScheduleFields(undefined);
      return;
    }
    void refreshSources(selectedCorpusId).catch((reason: unknown) => {
      setSources([]);
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  }, [selectedCorpusId]);

  async function run(action: () => Promise<void>) {
    try {
      setWorking(true);
      setError(null);
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function createCorpus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(async () => {
      const created = await knowledgeFabricApi.createGlobalCorpus({
        name: corpusName,
        description: corpusDescription,
        default_authority_profile: "standard"
      });
      setCorpusName("");
      setCorpusDescription("");
      setCorpora((current) => [...current, created]);
      setSelectedCorpusId(created.id);
    });
  }

  function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCorpus) return;
    void run(async () => {
      await knowledgeFabricApi.createGlobalSource(selectedCorpus.id, {
        source_type: sourceType,
        locator: sourceLocator,
        authority_profile: "standard"
      });
      setSourceType("");
      setSourceLocator("");
      await refreshSources(selectedCorpus.id);
    });
  }

  function saveSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scheduleSourceId) return;
    void run(async () => {
      await knowledgeFabricApi.configureExternalSourceSchedule(scheduleSourceId, {
        enabled: scheduleEnabled === "true",
        interval_seconds: Number(scheduleInterval)
      });
      if (selectedCorpus) await refreshSources(selectedCorpus.id);
    });
  }

  function retryDerivedWork(source: KnowledgeFabricOperationalSource) {
    void run(async () => {
      await knowledgeFabricApi.retryFailedDerivedWork(source.id);
      if (selectedCorpus) await refreshSources(selectedCorpus.id);
    });
  }

  return (
    <div className="settings-panel-stack" data-testid="knowledge-fabric-administration">
      <section className="settings-paper-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon settings-card-icon-mint">
            <StickyLabel variant="memory">KF</StickyLabel>
          </span>
          <div>
            <p className="settings-card-kicker">Global library</p>
            <h3>Knowledge Fabric</h3>
            <p>
              Global Corpora are managed once here. Server grants and Character policies remain
              scoped to their own Deployment Workspace.
            </p>
          </div>
        </div>
        {error && <Toast tone="danger" title="Knowledge Fabric operation failed">{error}</Toast>}
        {loading ? (
          <Spinner label="Loading global Corpus library" />
        ) : (
          <FormField label="Global Corpus">
            <Select
              aria-label="Global Corpus"
              value={selectedCorpusId}
              disabled={working || corpora.length === 0}
              onChange={(event) => setSelectedCorpusId(event.currentTarget.value)}
            >
              {corpora.length === 0 && <option value="">No Global Corpus registered</option>}
              {corpora.map((corpus) => (
                <option key={corpus.id} value={corpus.id}>{corpus.name}</option>
              ))}
            </Select>
          </FormField>
        )}
        <form className="settings-inline-form" onSubmit={createCorpus}>
          <FormField label="New Global Corpus" required>
            <Input
              required
              maxLength={200}
              value={corpusName}
              onChange={(event) => setCorpusName(event.currentTarget.value)}
            />
          </FormField>
          <FormField label="Description">
            <Textarea
              rows={2}
              maxLength={20000}
              value={corpusDescription}
              onChange={(event) => setCorpusDescription(event.currentTarget.value)}
            />
          </FormField>
          <Button type="submit" variant="primary" disabled={working}>Create Global Corpus</Button>
        </form>
      </section>

      {selectedCorpus && (
        <>
          <section className="settings-paper-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon settings-card-icon-peach">
                {selectedCorpus.owner_type.toUpperCase()}
              </span>
              <div>
                <p className="settings-card-kicker">Selected Corpus</p>
                <h3>{selectedCorpus.name}</h3>
                <p>{selectedCorpus.description || "No description provided."}</p>
              </div>
            </div>
            <form className="settings-inline-form" onSubmit={createSource}>
              <FormField label="Source type" required>
                <Input
                  required
                  maxLength={40}
                  value={sourceType}
                  onChange={(event) => setSourceType(event.currentTarget.value)}
                />
              </FormField>
              <FormField
                label="HTTPS locator"
                hint="Credentials and query parameters are rejected by the API."
                required
              >
                <Input
                  required
                  type="url"
                  maxLength={1000}
                  value={sourceLocator}
                  onChange={(event) => setSourceLocator(event.currentTarget.value)}
                />
              </FormField>
              <Button type="submit" variant="secondary" disabled={working}>Register Source</Button>
            </form>
          </section>

          <section className="settings-paper-card">
            <div className="settings-card-heading">
              <span className="settings-card-icon"><StickyLabel variant="memory">HEALTH</StickyLabel></span>
              <div>
                <p className="settings-card-kicker">Operational inspection</p>
                <h3>Source health</h3>
                <p>
                  Only source-backed, redacted state is displayed. Locators, profiles, artifacts,
                  validators, leases, and credentials stay private.
                </p>
              </div>
            </div>
            <div className="settings-list">
              {sources.map((source) => (
                <article className="settings-list-row" key={source.id}>
                  <div>
                    <strong>{source.source_type} · {source.authority_profile}</strong>
                    <span>
                      Last checked: {formatTimestamp(source.last_checked_at)} · Changed: {formatTimestamp(source.last_changed_at)}
                    </span>
                    <small>
                      Sync: {source.external_sync?.last_outcome ?? "not recorded"}
                      {source.external_sync?.last_error_code
                        ? ` (${source.external_sync.last_error_code})`
                        : ""}
                    </small>
                    <small>
                      Schedule: {source.external_schedule?.enabled
                        ? `enabled / ${source.external_schedule.interval_seconds}s`
                        : "disabled"}
                    </small>
                    <small>
                      Derived work: {source.derived_work.pending} pending · {source.derived_work.running} running · {source.derived_work.failed} failed
                    </small>
                  </div>
                  <div className="knowledge-card-actions">
                    <StatusIndicator tone={source.status === "available" ? "success" : "warning"}>
                      {source.status}
                    </StatusIndicator>
                    {source.derived_work.failed > 0 && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={working}
                        onClick={() => retryDerivedWork(source)}
                      >
                        Retry derived work
                      </Button>
                    )}
                  </div>
                </article>
              ))}
              {!loading && sources.length === 0 && (
                <EmptyState
                  title="No registered Sources"
                  description="Register an HTTPS Source before configuring its durable schedule."
                />
              )}
            </div>
          </section>

          {sources.length > 0 && (
            <section className="settings-paper-card">
              <div className="settings-card-heading">
                <span className="settings-card-icon settings-card-icon-mint">SYNC</span>
                <div>
                  <p className="settings-card-kicker">Durable schedule</p>
                  <h3>External sync schedule</h3>
                  <p>
                    This changes schedule state only. It does not promise a retry, rebuild,
                    publication, or index operation.
                  </p>
                </div>
              </div>
              <form className="settings-inline-form" onSubmit={saveSchedule}>
                <FormField label="Source">
                  <Select
                    value={scheduleSourceId}
                    onChange={(event) => {
                      const source = sources.find(
                        (item) => item.id === event.currentTarget.value
                      );
                      setScheduleSourceId(event.currentTarget.value);
                      setScheduleFields(source);
                    }}
                    disabled={working}
                  >
                    {sources.map((source) => (
                      <option key={source.id} value={source.id}>
                        {source.source_type} · {source.id}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="Schedule">
                  <Select
                    value={scheduleEnabled}
                    onChange={(event) => setScheduleEnabled(event.currentTarget.value)}
                    disabled={working}
                  >
                    <option value="false">Disabled</option>
                    <option value="true">Enabled</option>
                  </Select>
                </FormField>
                <FormField label="Interval seconds" hint="900–604800">
                  <Input
                    type="number"
                    min={900}
                    max={604800}
                    required
                    value={scheduleInterval}
                    onChange={(event) => setScheduleInterval(event.currentTarget.value)}
                    disabled={working}
                  />
                </FormField>
                <Button type="submit" variant="secondary" disabled={working}>Save schedule</Button>
              </form>
            </section>
          )}
        </>
      )}
    </div>
  );
}
