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
import type { CharacterDeployment, DiscordServerProfile } from "./deploymentApi";
import {
  knowledgeFabricApi,
  type KnowledgeFabricCharacterCorpusPolicy,
  type KnowledgeFabricCorpus,
  type KnowledgeFabricGlobalCorpusAccess,
  type KnowledgeFabricOverlayMode,
  type KnowledgeFabricQueryInspectorResult,
  type KnowledgeFabricScope,
  type KnowledgeFabricSource
} from "./knowledgeFabricApi";
import { nextGlobalCorpusGrantEnabled } from "./knowledgeFabricPanelPolicy";

interface Props {
  profile: DiscordServerProfile | undefined;
  deployments: CharacterDeployment[];
  demoMode: boolean;
  zh: boolean;
}

export function scopeMatchesProfile(
  scope: KnowledgeFabricScope,
  profile: DiscordServerProfile
): boolean {
  return (
    scope.platform === "discord" &&
    scope.connection_id === profile.connection_id &&
    scope.workspace_id === profile.guild_id
  );
}

function profileKey(profile: DiscordServerProfile | undefined): string {
  return profile ? `${profile.id}:${profile.connection_id}:${profile.guild_id}` : "";
}

function isServerLocal(corpus: KnowledgeFabricCorpus): boolean {
  return corpus.owner_type === "server";
}

export function KnowledgeFabricPanel({ profile, deployments, demoMode, zh }: Props) {
  const [scope, setScope] = useState<KnowledgeFabricScope | null>(null);
  const [loadedProfileKey, setLoadedProfileKey] = useState("");
  const [corpora, setCorpora] = useState<KnowledgeFabricCorpus[]>([]);
  const [available, setAvailable] = useState<KnowledgeFabricCorpus[]>([]);
  const [globalAccess, setGlobalAccess] = useState<KnowledgeFabricGlobalCorpusAccess[]>([]);
  const [policies, setPolicies] = useState<KnowledgeFabricCharacterCorpusPolicy[]>([]);
  const [sources, setSources] = useState<KnowledgeFabricSource[]>([]);
  const [selectedCorpusId, setSelectedCorpusId] = useState("");
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [sourceLocator, setSourceLocator] = useState("");
  const [inspectionQuery, setInspectionQuery] = useState("");
  const [inspectionMode, setInspectionMode] = useState("overview");
  const [inspection, setInspection] = useState<KnowledgeFabricQueryInspectorResult | null>(null);
  const loadVersion = useRef(0);

  const currentProfileKey = profileKey(profile);
  const activeScope = profile && scope && scopeMatchesProfile(scope, profile) ? scope : null;
  const selectedCorpus =
    activeScope && corpora.find((corpus) => corpus.id === selectedCorpusId) ?
      corpora.find((corpus) => corpus.id === selectedCorpusId) ?? null :
      null;

  async function load() {
    const version = ++loadVersion.current;
    if (!profile) {
      setScope(null);
      setCorpora([]);
      setAvailable([]);
      setGlobalAccess([]);
      setPolicies([]);
      setSources([]);
      setSelectedCorpusId("");
      setLoadedProfileKey("");
      return;
    }

    setLoading(true);
    try {
      const scopes = await knowledgeFabricApi.listScopes();
      const matched = scopes.find((item) => scopeMatchesProfile(item, profile)) ?? null;
      if (version !== loadVersion.current) return;

      if (!matched) {
        setScope(null);
        setCorpora([]);
        setAvailable([]);
        setGlobalAccess([]);
        setPolicies([]);
        setSources([]);
        setSelectedCorpusId("");
        setLoadedProfileKey(profileKey(profile));
        setError(null);
        return;
      }

      const [nextCorpora, nextAvailable, nextGlobalAccess, nextPolicies] = await Promise.all([
        knowledgeFabricApi.listCorpora(matched.id),
        knowledgeFabricApi.listAvailableGlobal(matched.id),
        knowledgeFabricApi.listGlobalAccess(matched.id),
        knowledgeFabricApi.listCharacterPolicies(matched.id)
      ]);
      if (version !== loadVersion.current) return;

      setScope(matched);
      setCorpora(nextCorpora);
      setAvailable(nextAvailable);
      setGlobalAccess(nextGlobalAccess);
      setPolicies(nextPolicies);
      setSelectedCorpusId((current) =>
        nextCorpora.some((corpus) => corpus.id === current) ? current : nextCorpora[0]?.id ?? ""
      );
      setLoadedProfileKey(profileKey(profile));
      setError(null);
    } catch (reason) {
      if (version === loadVersion.current) {
        setError(reason instanceof Error ? reason.message : String(reason));
        setLoadedProfileKey(profileKey(profile));
      }
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [profile?.id, profile?.connection_id, profile?.guild_id]);

  useEffect(() => {
    if (!activeScope || !selectedCorpus || !isServerLocal(selectedCorpus)) {
      setSources([]);
      return;
    }
    let cancelled = false;
    void knowledgeFabricApi
      .listLocalSources(activeScope.id, selectedCorpus.id)
      .then((nextSources) => {
        if (!cancelled) setSources(nextSources);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setSources([]);
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeScope?.id, selectedCorpus?.id, selectedCorpus?.owner_type]);

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

  async function setGlobalGrant(corpus: KnowledgeFabricCorpus, currentlyEnabled: boolean) {
    if (!activeScope) return;
    await run(async () => {
      await knowledgeFabricApi.grantGlobal(
        activeScope.id,
        corpus.id,
        nextGlobalCorpusGrantEnabled(currentlyEnabled)
      );
      await load();
    });
  }

  async function setOverlay(corpus: KnowledgeFabricCorpus, mode: KnowledgeFabricOverlayMode) {
    if (!activeScope) return;
    await run(async () => {
      await knowledgeFabricApi.setOverlay(activeScope.id, corpus.id, mode);
      await load();
    });
  }

  async function createCorpus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeScope) return;
    await run(async () => {
      const created = await knowledgeFabricApi.createLocalCorpus(activeScope.id, {
        name,
        description,
        default_authority_profile: "standard"
      });
      setName("");
      setDescription("");
      setSelectedCorpusId(created.id);
      await load();
    });
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeScope || !selectedCorpus || !isServerLocal(selectedCorpus)) return;
    await run(async () => {
      const created = await knowledgeFabricApi.createLocalSource(activeScope.id, selectedCorpus.id, {
        source_type: sourceType,
        locator: sourceLocator,
        authority_profile: "standard"
      });
      setSourceType("");
      setSourceLocator("");
      setSources((current) => [...current, created]);
    });
  }

  async function setCharacterPolicy(
    deployment: CharacterDeployment,
    corpusId: string,
    effect: "allow" | "deny"
  ) {
    if (!activeScope) return;
    await run(async () => {
      const next = await knowledgeFabricApi.setCharacterPolicy(
        activeScope.id,
        deployment.id,
        corpusId,
        effect
      );
      setPolicies((current) => [
        ...current.filter(
          (policy) =>
            !(
              policy.deployment_id === next.deployment_id && policy.corpus_id === next.corpus_id
            )
        ),
        next
      ]);
    });
  }

  async function inspectQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeScope) return;
    await run(async () => {
      setInspection(
        await knowledgeFabricApi.inspectQuery(activeScope.id, {
          query: inspectionQuery,
          mode: inspectionMode
        })
      );
    });
  }

  if (!profile) {
    return <EmptyState title={zh ? "先选择一个 Discord Server" : "Select a Discord server first"} />;
  }
  if (loading || loadedProfileKey !== currentProfileKey) {
    return (
      <EmptyState
        title={zh ? "正在打开 Knowledge Fabric…" : "Opening Knowledge Fabric…"}
        illustration={<Spinner label="Loading" />}
      />
    );
  }
  if (!activeScope) {
    return (
      <EmptyState
        title={zh ? "此 Server 尚未启用 Knowledge Fabric" : "Knowledge Fabric is not bootstrapped for this server"}
        description={
          zh
            ? "需要 Super Admin 先建立该 Server 的 Fabric scope；系统不会回退到旧 RAG。"
            : "A Super Admin must bootstrap the Fabric server scope; this page never falls back to legacy RAG."
        }
      />
    );
  }

  return (
    <section className="paper-sheet knowledge-panel knowledge-v3-panel">
      <div className="panel-heading-row knowledge-panel-heading">
        <div>
          <StickyLabel variant="memory">KNOWLEDGE FABRIC</StickyLabel>
          <h2>{zh ? "知识库" : "Knowledge Fabric"}</h2>
          <p>
            {zh
              ? "Corpus、Source 与角色知识边界由服务器授权和 Character policy 共同决定。"
              : "Corpus, Source, and Character knowledge boundaries are governed by server authorization and Character policy."}
          </p>
        </div>
      </div>

      {error && (
        <Toast tone="danger" title={zh ? "Knowledge Fabric 操作失败" : "Knowledge Fabric operation failed"}>
          {error}
        </Toast>
      )}

      <div className="knowledge-layout">
        <div className="knowledge-base-list">
          {corpora.map((corpus) => (
            <article
              className={`knowledge-base-card${selectedCorpus?.id === corpus.id ? " is-selected" : ""}`}
              key={corpus.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedCorpusId(corpus.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedCorpusId(corpus.id);
                }
              }}
            >
              <div>
                <StickyLabel variant="memory">{corpus.owner_type.toUpperCase()}</StickyLabel>
                <strong>{corpus.name}</strong>
                <span>
                  {corpus.default_authority_profile} · {corpus.overlay_mode ?? "inherit"}
                </span>
                {corpus.description && <small>{corpus.description}</small>}
              </div>
              <StatusIndicator tone="success">{corpus.status}</StatusIndicator>
              {!demoMode && !isServerLocal(corpus) && (
                <FormField label={zh ? "Server overlay" : "Server overlay"}>
                  <Select
                    value={corpus.overlay_mode ?? "inherit"}
                    aria-label={`Server overlay for ${corpus.name}`}
                    disabled={working}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) =>
                      void setOverlay(corpus, event.currentTarget.value as KnowledgeFabricOverlayMode)
                    }
                  >
                    <option value="inherit">{zh ? "继承" : "Inherit"}</option>
                    <option value="augment">{zh ? "增强" : "Augment"}</option>
                    <option value="override">{zh ? "覆盖" : "Override"}</option>
                    <option value="deny">{zh ? "拒绝" : "Deny"}</option>
                  </Select>
                </FormField>
              )}
            </article>
          ))}
          {corpora.length === 0 && (
            <EmptyState title={zh ? "尚无可用 Corpus" : "No accessible Corpus"} />
          )}
        </div>

        <div className="knowledge-document-panel">
          <strong>{zh ? "全局 Corpus 授权" : "Global Corpus grants"}</strong>
          {available.map((corpus) => {
            const access = globalAccess.find((item) => item.corpus_id === corpus.id);
            const enabled = access?.enabled ?? false;
            return (
              <article className="knowledge-document-card" key={corpus.id}>
                <div>
                  <strong>{corpus.name}</strong>
                  {corpus.description && <small>{corpus.description}</small>}
                </div>
                {!demoMode && (
                  <div className="knowledge-card-actions">
                    <Button
                      type="button"
                      size="sm"
                      variant={enabled ? "danger" : "secondary"}
                      disabled={working}
                      onClick={() => void setGlobalGrant(corpus, enabled)}
                    >
                      {enabled ? (zh ? "撤销授权" : "Revoke") : zh ? "授权" : "Grant"}
                    </Button>
                    {enabled && (
                      <Select
                        aria-label={`Server overlay for ${corpus.name}`}
                        value={access?.overlay_mode ?? "inherit"}
                        disabled={working}
                        onChange={(event) =>
                          void setOverlay(
                            corpus,
                            event.currentTarget.value as KnowledgeFabricOverlayMode
                          )
                        }
                      >
                        <option value="inherit">{zh ? "继承" : "Inherit"}</option>
                        <option value="augment">{zh ? "增强" : "Augment"}</option>
                        <option value="override">{zh ? "覆盖" : "Override"}</option>
                        <option value="deny">{zh ? "拒绝" : "Deny"}</option>
                      </Select>
                    )}
                  </div>
                )}
              </article>
            );
          })}
          {available.length === 0 && (
            <small>{zh ? "没有可授权的全局 Corpus。" : "No global Corpus is available."}</small>
          )}
        </div>
      </div>

      {!demoMode && (
        <form className="knowledge-create-form" onSubmit={createCorpus}>
          <FormField label={zh ? "新建 Server-local Corpus" : "New server-local Corpus"} required>
            <Input required maxLength={200} value={name} onChange={(event) => setName(event.currentTarget.value)} />
          </FormField>
          <FormField label={zh ? "说明" : "Description"}>
            <Textarea
              rows={3}
              maxLength={20000}
              value={description}
              onChange={(event) => setDescription(event.currentTarget.value)}
            />
          </FormField>
              <Button type="submit" variant="primary" disabled={working}>
            {zh ? "建立 Corpus" : "Create Corpus"}
          </Button>
        </form>
      )}

      {selectedCorpus && (
        <section className="knowledge-document-panel">
          <div className="panel-heading-row">
            <div>
              <StickyLabel variant="link">SOURCE</StickyLabel>
              <strong>{selectedCorpus.name}</strong>
              <small>
                {isServerLocal(selectedCorpus)
                  ? zh
                    ? "Server-local Source"
                    : "Server-local Sources"
                  : zh
                    ? "全局 Source 由 Super Admin 管理"
                    : "Global Sources are managed by a Super Admin"}
              </small>
            </div>
          </div>
          {isServerLocal(selectedCorpus) && (
            <>
              <div className="knowledge-document-list">
                {sources.map((source) => (
                  <article className="knowledge-document-card" key={source.id}>
                    <div>
                      <StickyLabel variant="link">{source.source_type.toUpperCase()}</StickyLabel>
                      <strong>{source.locator}</strong>
                      <small>{source.authority_profile}</small>
                    </div>
                    <StatusIndicator tone={source.enabled ? "success" : "neutral"}>
                      {source.status}
                    </StatusIndicator>
                  </article>
                ))}
                {sources.length === 0 && (
                  <EmptyState
                    title={zh ? "尚无 Source" : "No Sources yet"}
                    description={
                      zh
                        ? "注册一个 HTTP(S) Source 后，后台同步和索引状态仍由 Runtime 决定。"
                        : "After a HTTP(S) Source is registered, runtime owns its sync and index state."
                    }
                  />
                )}
              </div>
              {!demoMode && (
                <form className="knowledge-create-form" onSubmit={createSource}>
                  <FormField label={zh ? "Source type" : "Source type"} required>
                    <Input
                      required
                      maxLength={40}
                      value={sourceType}
                      onChange={(event) => setSourceType(event.currentTarget.value)}
                    />
                  </FormField>
                  <FormField
                    label={zh ? "HTTP(S) locator" : "HTTP(S) locator"}
                    hint={zh ? "不包含查询参数或凭据。" : "No query parameters or credentials."}
                    required
                  >
                    <Input
                      type="url"
                      required
                      maxLength={1000}
                      value={sourceLocator}
                      onChange={(event) => setSourceLocator(event.currentTarget.value)}
                    />
                  </FormField>
                  <Button type="submit" variant="primary" disabled={working}>
                    {zh ? "注册 Source" : "Register Source"}
                  </Button>
                </form>
              )}
            </>
          )}
        </section>
      )}

      <section className="knowledge-document-panel">
        <div className="panel-heading-row">
          <div>
            <StickyLabel variant="memory">INSPECTOR</StickyLabel>
            <strong>{zh ? "Scoped Query Inspector" : "Scoped Query Inspector"}</strong>
            <small>
              {zh
                ? "检索仅使用此 Server 已获授权的 Corpus；不会创建第二条查询路径。"
                : "Retrieval uses only this Server's authorized Corpora and never creates another query path."}
            </small>
          </div>
        </div>
        <form className="knowledge-create-form" onSubmit={inspectQuery}>
          <FormField label={zh ? "Query" : "Query"} required>
            <Textarea
              required
              rows={3}
              value={inspectionQuery}
              onChange={(event) => setInspectionQuery(event.currentTarget.value)}
            />
          </FormField>
          <FormField label={zh ? "Mode" : "Mode"}>
            <Select
              value={inspectionMode}
              onChange={(event) => setInspectionMode(event.currentTarget.value)}
              disabled={working}
            >
              <option value="overview">Overview</option>
              <option value="exact">Exact</option>
              <option value="relational">Relational</option>
              <option value="current">Current</option>
              <option value="code">Code</option>
            </Select>
          </FormField>
          <Button type="submit" variant="secondary" disabled={working}>
            {zh ? "Inspect" : "Inspect"}
          </Button>
        </form>
        {inspection && (
          <div className="knowledge-document-list">
            <small>
              {inspection.mode} · {inspection.accessible_corpus_count}{" "}
              {zh ? "个可访问 Corpus" : "accessible Corpora"} · {inspection.freshness_status}
            </small>
            {inspection.hits.map((hit) => (
              <article className="knowledge-document-card" key={hit.evidence_unit_id}>
                <div>
                  <strong>{hit.document_title}</strong>
                  <small>{hit.authority_profile} · {hit.channels.join(", ") || "no channel"}</small>
                  <small>{hit.evidence_unit_id} · {hit.source_version_id}</small>
                  <p>{hit.text_content}</p>
                </div>
              </article>
            ))}
            {inspection.hits.length === 0 && (
              <EmptyState title={zh ? "没有匹配 Evidence" : "No matching Evidence"} />
            )}
          </div>
        )}
      </section>

      <section className="knowledge-document-panel">
        <div className="panel-heading-row">
          <div>
            <StickyLabel variant="warning">CHARACTER POLICY</StickyLabel>
            <strong>{zh ? "Character 知识边界" : "Character knowledge boundary"}</strong>
            <small>
              {zh
                ? "没有明确 allow 的 Corpus 不会被该 Character 使用；deny 优先。"
                : "A Character cannot use a Corpus without an explicit allow; deny wins."}
            </small>
          </div>
        </div>
        {deployments.length === 0 || corpora.length === 0 ? (
          <EmptyState
            title={zh ? "部署和 Corpus 都准备好后可设置" : "Available once deployments and Corpora exist"}
          />
        ) : (
          <div className="knowledge-document-list">
            {deployments.map((deployment) => (
              <article className="knowledge-document-card" key={deployment.id}>
                <div>
                  <strong>{deployment.character_display_name}</strong>
                  <small>{deployment.status}</small>
                </div>
                {!demoMode && (
                  <FormField label={zh ? "Corpus" : "Corpus"}>
                    <Select
                      aria-label={`${deployment.character_display_name} Corpus`}
                      disabled={working}
                      onChange={(event) => {
                        const [corpusId, effect] = event.currentTarget.value.split(":", 2);
                        if (corpusId && (effect === "allow" || effect === "deny")) {
                          void setCharacterPolicy(deployment, corpusId, effect);
                        }
                      }}
                      value=""
                    >
                      <option value="">{zh ? "设置 Corpus policy" : "Set a Corpus policy"}</option>
                      {corpora.flatMap((corpus) => {
                        const current = policies.find(
                          (policy) =>
                            policy.deployment_id === deployment.id && policy.corpus_id === corpus.id
                        );
                        return [
                          <option key={`${corpus.id}:allow`} value={`${corpus.id}:allow`}>
                            {corpus.name} · {current?.effect === "allow" ? "allow ✓" : "allow"}
                          </option>,
                          <option key={`${corpus.id}:deny`} value={`${corpus.id}:deny`}>
                            {corpus.name} · {current?.effect === "deny" ? "deny ✓" : "deny"}
                          </option>
                        ];
                      })}
                    </Select>
                  </FormField>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
