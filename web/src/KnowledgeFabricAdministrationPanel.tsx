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
  type KnowledgeFabricCanonicalEntity,
  type KnowledgeFabricCorpus,
  type KnowledgeFabricImageAssetCandidate,
  type KnowledgeFabricOperationalSource,
  type KnowledgeFabricVisualReference
} from "./knowledgeFabricApi";

const SOURCE_OPTIONS = [
  {
    value: "website_collection_public_https",
    label: "Wiki or website collection",
    note: "Starts at one public HTTPS page and discovers a bounded same-site collection."
  },
  {
    value: "website_public_https",
    label: "Single public web page",
    note: "Keeps one public HTTPS page under review."
  },
  {
    value: "atom_public_https",
    label: "Atom feed",
    note: "Uses an Atom feed as the source-native update boundary."
  }
] as const;

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not checked yet";
}

function sourceOptionNote(sourceType: string): string {
  return SOURCE_OPTIONS.find((option) => option.value === sourceType)?.note ?? "";
}

function syncOutcome(source: KnowledgeFabricOperationalSource): string {
  if (source.external_sync?.last_error_code) return source.external_sync.last_error_code;
  return source.external_sync?.last_outcome ?? "Waiting for the first sync";
}

export function KnowledgeFabricAdministrationPanel() {
  const [corpora, setCorpora] = useState<KnowledgeFabricCorpus[]>([]);
  const [sources, setSources] = useState<KnowledgeFabricOperationalSource[]>([]);
  const [entities, setEntities] = useState<KnowledgeFabricCanonicalEntity[]>([]);
  const [candidates, setCandidates] = useState<KnowledgeFabricImageAssetCandidate[]>([]);
  const [references, setReferences] = useState<KnowledgeFabricVisualReference[]>([]);
  const [selectedCorpusId, setSelectedCorpusId] = useState("");
  const [loading, setLoading] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [corpusName, setCorpusName] = useState("");
  const [corpusDescription, setCorpusDescription] = useState("");
  const [sourceType, setSourceType] = useState<(typeof SOURCE_OPTIONS)[number]["value"]>(
    "website_collection_public_https"
  );
  const [sourceLocator, setSourceLocator] = useState("");
  const [scheduleSourceId, setScheduleSourceId] = useState("");
  const [scheduleEnabled, setScheduleEnabled] = useState("false");
  const [scheduleInterval, setScheduleInterval] = useState("900");
  const [entityName, setEntityName] = useState("");
  const [entityAliases, setEntityAliases] = useState("");
  const [referenceEntityId, setReferenceEntityId] = useState("");
  const [referenceCandidateId, setReferenceCandidateId] = useState("");
  const [comparisonAuthorized, setComparisonAuthorized] = useState("false");
  const corpusRequestVersion = useRef(0);
  const workspaceRequestVersion = useRef(0);

  const selectedCorpus = corpora.find((corpus) => corpus.id === selectedCorpusId) ?? null;
  const selectedEntity = entities.find((entity) => entity.id === referenceEntityId) ?? null;
  const selectedCandidate = candidates.find((candidate) => candidate.asset_id === referenceCandidateId) ?? null;

  async function loadCorpora() {
    const version = ++corpusRequestVersion.current;
    setLoading(true);
    try {
      const nextCorpora = await knowledgeFabricApi.listGlobalCorpora();
      if (version !== corpusRequestVersion.current) return;
      setCorpora(nextCorpora);
      setSelectedCorpusId((current) =>
        nextCorpora.some((corpus) => corpus.id === current)
          ? current
          : nextCorpora[0]?.id ?? ""
      );
      setError(null);
    } catch (reason) {
      if (version === corpusRequestVersion.current) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (version === corpusRequestVersion.current) setLoading(false);
    }
  }

  useEffect(() => {
    void loadCorpora();
  }, []);

  function setScheduleFields(source: KnowledgeFabricOperationalSource | undefined) {
    setScheduleEnabled(source?.external_schedule?.enabled ? "true" : "false");
    setScheduleInterval(String(source?.external_schedule?.interval_seconds ?? 900));
  }

  async function refreshWorkspace(corpusId: string): Promise<void> {
    const version = ++workspaceRequestVersion.current;
    setWorkspaceLoading(true);
    try {
      const [nextSources, nextEntities, nextCandidates, nextReferences] = await Promise.all([
        knowledgeFabricApi.listGlobalOperationalSources(corpusId),
        knowledgeFabricApi.listGlobalCanonicalEntities(corpusId),
        knowledgeFabricApi.listGlobalImageAssetCandidates(corpusId),
        knowledgeFabricApi.listGlobalVisualReferences(corpusId)
      ]);
      if (version !== workspaceRequestVersion.current) return;
      setSources(nextSources);
      setEntities(nextEntities);
      setCandidates(nextCandidates);
      setReferences(nextReferences);
      const nextScheduleSource = nextSources.find((source) => source.id === scheduleSourceId)
        ?? nextSources[0];
      setScheduleSourceId(nextScheduleSource?.id ?? "");
      setScheduleFields(nextScheduleSource);
      setReferenceEntityId((current) =>
        nextEntities.some((entity) => entity.id === current) ? current : nextEntities[0]?.id ?? ""
      );
      setReferenceCandidateId((current) =>
        nextCandidates.some((candidate) => candidate.asset_id === current)
          ? current
          : nextCandidates[0]?.asset_id ?? ""
      );
      setError(null);
    } catch (reason) {
      if (version === workspaceRequestVersion.current) {
        setSources([]);
        setEntities([]);
        setCandidates([]);
        setReferences([]);
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      if (version === workspaceRequestVersion.current) setWorkspaceLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedCorpusId) {
      workspaceRequestVersion.current += 1;
      setSources([]);
      setEntities([]);
      setCandidates([]);
      setReferences([]);
      return;
    }
    void refreshWorkspace(selectedCorpusId);
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
      setSourceLocator("");
      await refreshWorkspace(selectedCorpus.id);
    });
  }

  function saveSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scheduleSourceId || !selectedCorpus) return;
    void run(async () => {
      await knowledgeFabricApi.configureExternalSourceSchedule(scheduleSourceId, {
        enabled: scheduleEnabled === "true",
        interval_seconds: Number(scheduleInterval)
      });
      await refreshWorkspace(selectedCorpus.id);
    });
  }

  function createEntity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCorpus) return;
    void run(async () => {
      const created = await knowledgeFabricApi.createGlobalCanonicalEntity(selectedCorpus.id, {
        entity_type: "fictional_character",
        canonical_name: entityName,
        aliases: entityAliases
          .split(/[\n,]/)
          .map((alias) => alias.trim())
          .filter(Boolean),
        metadata: {}
      });
      setEntityName("");
      setEntityAliases("");
      setEntities((current) => [...current, created]);
      setReferenceEntityId(created.id);
    });
  }

  function approveReference(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCorpus || !selectedEntity || !selectedCandidate) return;
    void run(async () => {
      const created = await knowledgeFabricApi.createGlobalVisualReference(selectedCorpus.id, {
        canonical_entity_id: selectedEntity.id,
        evidence_unit_id: selectedCandidate.evidence_unit_id,
        asset_id: selectedCandidate.asset_id,
        descriptor: selectedCandidate.caption ? { caption: selectedCandidate.caption } : {},
        comparison_authorized:
          selectedEntity.entity_type === "fictional_character" && comparisonAuthorized === "true"
      });
      setReferences((current) => [...current, created]);
    });
  }

  function retryDerivedWork(source: KnowledgeFabricOperationalSource) {
    if (!selectedCorpus) return;
    void run(async () => {
      await knowledgeFabricApi.retryFailedDerivedWork(source.id);
      await refreshWorkspace(selectedCorpus.id);
    });
  }

  function revokeReference(reference: KnowledgeFabricVisualReference) {
    if (!selectedCorpus) return;
    void run(async () => {
      await knowledgeFabricApi.revokeGlobalVisualReference(selectedCorpus.id, reference.id);
      setReferences((current) => current.filter((item) => item.id !== reference.id));
    });
  }

  return (
    <div className="settings-panel-stack knowledge-fabric-admin" data-testid="knowledge-fabric-administration">
      <section className="settings-paper-card knowledge-fabric-hero">
        <div className="settings-card-heading">
          <span className="settings-card-icon settings-card-icon-mint"><StickyLabel variant="memory">KF</StickyLabel></span>
          <div>
            <p className="settings-card-kicker">Global library</p>
            <h3>Build a world reference, not another admin form.</h3>
            <p>Add one public Wiki or site, let the bounded collector keep it current, then review the character references that make Discord image context useful.</p>
          </div>
        </div>
        <ol className="knowledge-fabric-steps" aria-label="Knowledge Fabric setup steps">
          <li className="is-active"><span>1</span> Choose a library</li>
          <li><span>2</span> Add a Wiki</li>
          <li><span>3</span> Review references</li>
        </ol>
        {error && <Toast tone="danger" title="Knowledge Fabric operation failed">{error}</Toast>}
      </section>

      <section className="settings-paper-card knowledge-fabric-library-card">
        <div className="settings-card-heading">
          <span className="settings-card-icon"><StickyLabel variant="memory">1</StickyLabel></span>
          <div><p className="settings-card-kicker">Library shelf</p><h3>Pick a world library</h3><p>Global content is stored once here; server grants and Character policy stay elsewhere.</p></div>
        </div>
        {loading ? <Spinner label="Loading global libraries" /> : (
          <div className="knowledge-fabric-library-layout">
            <FormField label="Global library">
              <Select aria-label="Global library" value={selectedCorpusId} disabled={working || corpora.length === 0} onChange={(event) => setSelectedCorpusId(event.currentTarget.value)}>
                {corpora.length === 0 && <option value="">No library yet</option>}
                {corpora.map((corpus) => <option key={corpus.id} value={corpus.id}>{corpus.name}</option>)}
              </Select>
            </FormField>
            {selectedCorpus && <aside className="knowledge-fabric-selection-note"><StickyLabel variant="memory">{selectedCorpus.status}</StickyLabel><strong>{selectedCorpus.name}</strong><span>{selectedCorpus.description || "A shared library ready for a first source."}</span></aside>}
          </div>
        )}
        <form className="knowledge-fabric-create-library" onSubmit={createCorpus}>
          <FormField label="New world library" required><Input required maxLength={200} placeholder="e.g. Teyvat reference" value={corpusName} onChange={(event) => setCorpusName(event.currentTarget.value)} /></FormField>
          <FormField label="A short note"><Input maxLength={20000} placeholder="What belongs in this collection?" value={corpusDescription} onChange={(event) => setCorpusDescription(event.currentTarget.value)} /></FormField>
          <Button type="submit" variant="primary" disabled={working}>Create library</Button>
        </form>
      </section>

      {selectedCorpus && <>
        <section className="settings-paper-card knowledge-fabric-source-card">
          <div className="settings-card-heading">
            <span className="settings-card-icon settings-card-icon-peach"><StickyLabel variant="link">2</StickyLabel></span>
            <div><p className="settings-card-kicker">Source notebook</p><h3>Paste a Wiki or public site</h3><p>Website collection is the recommended Wiki option: it follows bounded same-site discovery instead of asking you to add every page.</p></div>
          </div>
          <form className="knowledge-fabric-source-form" onSubmit={createSource}>
            <FormField label="What are you adding?"><Select value={sourceType} disabled={working} onChange={(event) => setSourceType(event.currentTarget.value as (typeof SOURCE_OPTIONS)[number]["value"])}>{SOURCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</Select></FormField>
            <FormField label="Public HTTPS link" hint="No login, query parameters, or credentials." required><Input required type="url" maxLength={1000} placeholder="https://example-wiki.org/wiki/" value={sourceLocator} onChange={(event) => setSourceLocator(event.currentTarget.value)} /></FormField>
            <Button type="submit" variant="primary" disabled={working}>Add to library</Button>
          </form>
          <p className="knowledge-fabric-field-note">{sourceOptionNote(sourceType)}</p>
        </section>

        <section className="settings-paper-card knowledge-fabric-source-status-card">
          <div className="settings-card-heading">
            <span className="settings-card-icon settings-card-icon-mint"><StickyLabel variant="memory">SYNC</StickyLabel></span>
            <div><p className="settings-card-kicker">Collection journal</p><h3>What the library is watching</h3><p>These are redacted operational facts, not invented crawl counts or progress.</p></div>
          </div>
          {workspaceLoading ? <Spinner label="Refreshing library state" /> : sources.length === 0 ? <EmptyState title="Your first source will appear here" description="Add a Wiki or public site above. Scheduling remains off until you choose to enable it." /> : <div className="knowledge-fabric-source-list">
            {sources.map((source) => <article className="knowledge-fabric-source-row" key={source.id}>
              <div className="knowledge-fabric-source-summary"><StickyLabel variant="link">{source.source_type.replaceAll("_", " ")}</StickyLabel><strong>{source.authority_profile} source</strong><span>Last checked {formatTimestamp(source.last_checked_at)}</span><small>{syncOutcome(source)}</small></div>
              <div className="knowledge-card-actions"><StatusIndicator tone={source.status === "available" ? "success" : "warning"}>{source.status}</StatusIndicator>{source.derived_work.failed > 0 && <Button size="sm" variant="secondary" disabled={working} onClick={() => retryDerivedWork(source)}>Retry review work</Button>}</div>
              {source.site_collection_summary && <dl className="knowledge-fabric-sync-report" aria-label="Latest site collection sync report">
                <div><dt>Last complete scan</dt><dd>{formatTimestamp(source.site_collection_summary.last_completed_at)}</dd></div>
                <div><dt>Current pages</dt><dd>{source.site_collection_summary.available_page_count}</dd></div>
                <div><dt>Pages checked</dt><dd>{source.site_collection_summary.checked_page_count}</dd></div>
                <div><dt>Failed pages</dt><dd>{source.site_collection_summary.failed_page_count}</dd></div>
                <div><dt>Removed pages</dt><dd>{source.site_collection_summary.removed_page_count}</dd></div>
                <div><dt>Next check</dt><dd>{formatTimestamp(source.external_schedule?.next_run_at ?? null)}</dd></div>
              </dl>}
            </article>)}
          </div>}
          {sources.length > 0 && <form className="knowledge-fabric-schedule-form" onSubmit={saveSchedule}>
            <FormField label="Source to check"><Select value={scheduleSourceId} disabled={working} onChange={(event) => { const source = sources.find((item) => item.id === event.currentTarget.value); setScheduleSourceId(event.currentTarget.value); setScheduleFields(source); }}>{sources.map((source) => <option key={source.id} value={source.id}>{source.source_type} · {source.status}</option>)}</Select></FormField>
            <FormField label="Automatic checks"><Select value={scheduleEnabled} disabled={working} onChange={(event) => setScheduleEnabled(event.currentTarget.value)}><option value="false">Keep off for now</option><option value="true">Check automatically</option></Select></FormField>
            <FormField label="Every (seconds)" hint="900–604800"><Input type="number" min={900} max={604800} required value={scheduleInterval} disabled={working} onChange={(event) => setScheduleInterval(event.currentTarget.value)} /></FormField>
            <Button type="submit" variant="secondary" disabled={working}>Save checking rule</Button>
          </form>}
        </section>

        <section className="settings-paper-card knowledge-fabric-reference-card">
          <div className="settings-card-heading">
            <span className="settings-card-icon"><StickyLabel variant="memory">3</StickyLabel></span>
            <div><p className="settings-card-kicker">Character reference desk</p><h3>Connect collected art to a character</h3><p>Private image files never appear in the browser; only safe provenance metadata is shown for approval.</p></div>
          </div>
          <div className="knowledge-fabric-reference-grid">
            <form className="knowledge-fabric-mini-form" onSubmit={createEntity}>
              <strong>1. Name the character</strong>
              <FormField label="Canonical name" required><Input required maxLength={500} placeholder="Amber" value={entityName} onChange={(event) => setEntityName(event.currentTarget.value)} /></FormField>
              <FormField label="Aliases" hint="Separate with commas or new lines."><Textarea rows={2} value={entityAliases} onChange={(event) => setEntityAliases(event.currentTarget.value)} /></FormField>
              <Button type="submit" size="sm" variant="secondary" disabled={working}>Add character</Button>
            </form>
            <form className="knowledge-fabric-mini-form" onSubmit={approveReference}>
              <strong>2. Approve collected evidence</strong>
              <FormField label="Character" required><Select value={referenceEntityId} disabled={working || entities.length === 0} onChange={(event) => setReferenceEntityId(event.currentTarget.value)}>{entities.length === 0 && <option value="">Add a character first</option>}{entities.map((entity) => <option key={entity.id} value={entity.id}>{entity.canonical_name}</option>)}</Select></FormField>
              <FormField label="Collected image evidence" required><Select value={referenceCandidateId} disabled={working || candidates.length === 0} onChange={(event) => setReferenceCandidateId(event.currentTarget.value)}>{candidates.length === 0 && <option value="">No collected images yet</option>}{candidates.map((candidate) => <option key={candidate.asset_id} value={candidate.asset_id}>{candidate.caption || candidate.document_locator}</option>)}</Select></FormField>
              <FormField label="Allow private multi-image comparison"><Select value={comparisonAuthorized} disabled={working || selectedEntity?.entity_type !== "fictional_character"} onChange={(event) => setComparisonAuthorized(event.currentTarget.value)}><option value="false">No — exact match / caption only</option><option value="true">Yes — fictional character only</option></Select></FormField>
              <p className="knowledge-fabric-consent-note">{selectedEntity?.entity_type === "fictional_character" ? "The configured provider receives an anonymous Discord image plus up to five approved private references; the character name stays local." : "Only fictional characters can be authorized for external visual comparison."}</p>
              <Button type="submit" size="sm" variant="primary" disabled={working || !selectedEntity || !selectedCandidate}>Approve reference</Button>
            </form>
          </div>
          <div className="knowledge-fabric-reference-list" aria-live="polite">
            {references.map((reference) => { const entity = entities.find((item) => item.id === reference.canonical_entity_id); return <article className="knowledge-fabric-reference-row" key={reference.id}><div><strong>{entity?.canonical_name ?? "Approved character"}</strong><span>{reference.descriptor.caption || "Approved source image"}</span><small>{reference.comparison_authorized ? "Multi-image comparison enabled" : "Exact match / caption only"}</small></div><Button type="button" size="sm" variant="danger" disabled={working} onClick={() => revokeReference(reference)}>Revoke</Button></article>; })}
            {references.length === 0 && <EmptyState title="No character references approved yet" description="They become available after a source collects image evidence." />}
          </div>
        </section>
      </>}
    </div>
  );
}
