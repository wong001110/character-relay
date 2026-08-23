import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import type { CharacterDeployment } from "./deploymentApi";
import {
  intelligenceProductApi,
  type DeploymentSocialIntelligence,
  type RelationshipStateObservation,
  type SocialTargetObservation
} from "./intelligenceProductApi";
import {
  relationshipApi,
  type CharacterRelationshipPrior,
  type RelationshipGeneration
} from "./relationshipApi";
import { pageCount, pageItems } from "./conversationPagination";
import { Pagination } from "./Pagination";

interface Props {
  cards: CharacterCard[];
  deployments: CharacterDeployment[];
  zh: boolean;
}

type SocialView = "lived" | "canonical";
type Dimension = "familiarity" | "affinity" | "trust" | "comfort";

const SOCIAL_TARGET_PAGE_SIZE = 10;

interface PriorDraft {
  relationship_type: string;
  description: string;
  familiarity: number;
  affinity: number;
  trust: number;
  comfort: number;
  rationale: string;
}

const dimensions: Dimension[] = ["familiarity", "affinity", "trust", "comfort"];

function emptyDraft(prior?: CharacterRelationshipPrior): PriorDraft {
  return {
    relationship_type: prior?.relationship_type ?? "other",
    description: prior?.description ?? "",
    familiarity: prior?.familiarity ?? 0,
    affinity: prior?.affinity ?? 0,
    trust: prior?.trust ?? 0,
    comfort: prior?.comfort ?? 0,
    rationale: ""
  };
}

function stamp(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

function score(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function dimensionLabel(value: Dimension, zh: boolean): string {
  const labels: Record<Dimension, [string, string]> = {
    familiarity: ["Familiarity", "熟悉度"],
    affinity: ["Affinity", "亲和/好感"],
    trust: ["Trust", "信任"],
    comfort: ["Comfort", "相处舒适度"]
  };
  return zh ? labels[value][1] : labels[value][0];
}

function baseline(state: RelationshipStateObservation, dimension: Dimension): number {
  if (dimension === "familiarity") return state.familiarity_baseline;
  if (dimension === "affinity") return state.affinity_baseline;
  if (dimension === "trust") return state.trust_baseline;
  return state.comfort_baseline;
}

function targetKindLabel(item: SocialTargetObservation): string {
  if (item.target_kind === "character") return "CHARACTER";
  if (item.target_kind === "bot") return "BOT";
  if (item.target_kind === "user") return "USER";
  return "UNKNOWN";
}

function RelationshipMeters({ item, zh }: { item: SocialTargetObservation; zh: boolean }) {
  const state = item.state;
  if (!state) {
    return <small>{zh ? "尚无 lived relationship state。" : "No lived relationship state yet."}</small>;
  }
  return (
    <div className="social-v2-meters">
      {dimensions.map((dimension) => {
        const current = state[dimension];
        return (
          <div className="social-v2-meter" key={dimension}>
            <div>
              <strong>{dimensionLabel(dimension, zh)}</strong>
              <span>{score(current)}</span>
            </div>
            <div className="social-v2-track"><i style={{ width: `${Math.min(100, Math.abs(current) * 100)}%` }} /></div>
            <small>baseline {score(baseline(state, dimension))}</small>
          </div>
        );
      })}
    </div>
  );
}

export function SocialIntelligencePanel({ cards, deployments, zh }: Props) {
  const [view, setView] = useState<SocialView>("lived");
  const [sourceDeploymentId, setSourceDeploymentId] = useState(
    deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
  );
  const [data, setData] = useState<DeploymentSocialIntelligence | null>(null);
  const [targetKey, setTargetKey] = useState("");
  const [targetPage, setTargetPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const sourceDeployment = deployments.find((item) => item.id === sourceDeploymentId) ?? null;
  const targetPages = pageCount(data?.items.length ?? 0, SOCIAL_TARGET_PAGE_SIZE);
  const visibleTargets = useMemo(
    () => pageItems(data?.items ?? [], targetPage, SOCIAL_TARGET_PAGE_SIZE),
    [data?.items, targetPage]
  );
  const selectedTarget = data?.items.find(
    (item) => `${item.target_type}:${item.target_key}` === targetKey
  ) ?? data?.items[0] ?? null;

  async function loadSocial(deploymentId = sourceDeploymentId) {
    if (!deploymentId) {
      setData(null);
      return;
    }
    try {
      setLoading(true);
      setError("");
      const next = await intelligenceProductApi.social(deploymentId);
      setData(next);
      setTargetKey((current) =>
        next.items.some((item) => `${item.target_type}:${item.target_key}` === current)
          ? current
          : next.items[0]
            ? `${next.items[0].target_type}:${next.items[0].target_key}`
            : ""
      );
      setTargetPage(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!deployments.some((item) => item.id === sourceDeploymentId)) {
      setSourceDeploymentId(
        deployments.find((item) => item.status === "active")?.id ?? deployments[0]?.id ?? ""
      );
    }
  }, [deployments, sourceDeploymentId]);

  useEffect(() => {
    void loadSocial();
  }, [sourceDeploymentId]);

  useEffect(() => {
    setTargetPage((current) => Math.min(Math.max(1, current), targetPages));
  }, [targetPages]);

  return (
    <section className="paper-sheet social-v2-panel">
      <header className="intelligence-product-heading">
        <div>
          <span className="tape-label">SOCIAL INTELLIGENCE V2</span>
          <h2>{zh ? "角色如何看待 Server 里的其他人" : "How Characters see people in this Server"}</h2>
          <p>
            {zh
              ? "Relationship State、Person Impression 与 Memory 是不同层。这里统一观察 Bot→User 与 Bot→Bot 的方向性 lived state；Canonical Relationship 则在 Card Authoring 中维护。"
              : "Relationship State, Person Impression, and Memory are separate layers. This view unifies directional Bot→User and Bot→Bot lived state; Canonical Relationships are maintained in Card Authoring."}
          </p>
        </div>
        <button type="button" className="paper-button" disabled={loading} onClick={() => void loadSocial()}>
          {zh ? "刷新" : "Refresh"}
        </button>
      </header>

      <nav className="intelligence-product-subtabs">
        <button type="button" className={view === "lived" ? "is-active" : ""} onClick={() => setView("lived")}>
          {zh ? "Lived Social State" : "Lived Social State"}
        </button>
        <button type="button" className={view === "canonical" ? "is-active" : ""} onClick={() => setView("canonical")}>
          {zh ? "Character Card 关系设定" : "Character Card Relationships"}
        </button>
      </nav>

      {error && <small className="deployment-inline-error">{error}</small>}

      {view === "lived" ? (
        <>
          <div className="social-v2-source-row">
            <label>
              <span>{zh ? "观察角色" : "Character"}</span>
              <select value={sourceDeploymentId} onChange={(event) => setSourceDeploymentId(event.currentTarget.value)}>
                {deployments.map((item) => (
                  <option key={item.id} value={item.id}>{item.character_display_name} · {item.status}</option>
                ))}
              </select>
            </label>
            <small>{zh ? "方向：观察角色 → 对方" : "Direction: selected Character → target"}</small>
          </div>

          {!sourceDeploymentId ? (
            <p>{zh ? "这个 Server 还没有 Character Deployment。" : "No Character Deployment exists in this Server."}</p>
          ) : loading && !data ? (
            <p>{zh ? "读取 Social Intelligence…" : "Loading Social Intelligence…"}</p>
          ) : !data || data.items.length === 0 ? (
            <div className="intelligence-empty-note">
              <strong>{zh ? "还没有 social evidence" : "No social evidence yet"}</strong>
              <p>{zh ? "有意义的直接互动会先建立 Familiarity；Affinity / Trust / Comfort 只在有对应证据时变化。" : "Meaningful direct interaction first establishes Familiarity. Affinity, Trust, and Comfort change only when corresponding evidence exists."}</p>
            </div>
          ) : (
            <div className="social-v2-layout">
              <aside className="social-v2-target-list">
                <div className="social-v2-target-list-items">
                  {visibleTargets.map((item) => {
                    const key = `${item.target_type}:${item.target_key}`;
                    return (
                      <button
                        type="button"
                        key={key}
                        className={key === `${selectedTarget?.target_type}:${selectedTarget?.target_key}` ? "is-active" : ""}
                        onClick={() => setTargetKey(key)}
                      >
                        {item.avatar_url ? <img src={item.avatar_url} alt="" /> : <span>{item.label.slice(0, 1).toUpperCase()}</span>}
                        <div><strong>{item.label}</strong><small>{targetKindLabel(item)}</small></div>
                      </button>
                    );
                  })}
                </div>
                <Pagination
                  page={targetPage}
                  pages={targetPages}
                  total={data.items.length}
                  onPage={(nextPage) => {
                    setTargetPage(nextPage);
                    const nextTarget = pageItems(data.items, nextPage, SOCIAL_TARGET_PAGE_SIZE)[0];
                    if (nextTarget) setTargetKey(`${nextTarget.target_type}:${nextTarget.target_key}`);
                  }}
                />
              </aside>

              {selectedTarget && (
                <article className="social-v2-detail">
                  <header>
                    <div>
                      <span>{targetKindLabel(selectedTarget)}</span>
                      <h3>{data.character_display_name} → {selectedTarget.label}</h3>
                    </div>
                    <small>{selectedTarget.state ? `${zh ? "最近证据" : "last evidence"} ${stamp(selectedTarget.state.last_evidence_at, zh)}` : "—"}</small>
                  </header>

                  <RelationshipMeters item={selectedTarget} zh={zh} />

                  <section className="social-v2-impression">
                    <span className="tape-label">PERSON IMPRESSION</span>
                    <h4>{zh ? `${data.character_display_name} 如何看待对方` : `How ${data.character_display_name} sees them`}</h4>
                    {selectedTarget.impression ? (
                      <>
                        <p>{selectedTarget.impression.summary || (zh ? "尚无摘要。" : "No summary yet.")}</p>
                        {selectedTarget.impression.observations.length > 0 && (
                          <ul>{selectedTarget.impression.observations.map((item) => <li key={item}>{item}</li>)}</ul>
                        )}
                        <small>confidence {selectedTarget.impression.confidence.toFixed(2)} · {stamp(selectedTarget.impression.updated_at, zh)}</small>
                      </>
                    ) : (
                      <p>{zh ? "目前只有关系证据，还没有可支持的 Person Impression。" : "Relationship evidence exists, but there is not yet enough evidence for a Person Impression."}</p>
                    )}
                  </section>

                  <section className="social-v2-evidence">
                    <span className="tape-label">RECENT EVIDENCE</span>
                    {selectedTarget.recent_evidence.length ? selectedTarget.recent_evidence.map((item, index) => (
                      <div key={`${item.recorded_at}:${index}`}>
                        <strong>{item.dimension} {item.delta >= 0 ? "+" : ""}{item.delta.toFixed(2)}</strong>
                        <span>{item.reason_code.replaceAll("_", " ")}</span>
                        <small>confidence {item.confidence.toFixed(2)} · {stamp(item.recorded_at, zh)}</small>
                      </div>
                    )) : <small>{zh ? "没有近期 evidence event。" : "No recent evidence events."}</small>}
                  </section>
                </article>
              )}
            </div>
          )}
        </>
      ) : (
        <CanonicalRelationshipAuthoring cards={cards} preferredSourceCardId={sourceDeployment?.character_card_id ?? ""} zh={zh} />
      )}
    </section>
  );
}

function CanonicalRelationshipAuthoring({
  cards,
  preferredSourceCardId,
  zh
}: {
  cards: CharacterCard[];
  preferredSourceCardId: string;
  zh: boolean;
}) {
  const [leftId, setLeftId] = useState(preferredSourceCardId || cards[0]?.id || "");
  const [rightId, setRightId] = useState(cards.find((item) => item.id !== (preferredSourceCardId || cards[0]?.id))?.id ?? "");
  const [forward, setForward] = useState<PriorDraft>(() => emptyDraft());
  const [reverse, setReverse] = useState<PriorDraft>(() => emptyDraft());
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const left = cards.find((item) => item.id === leftId) ?? null;
  const right = cards.find((item) => item.id === rightId) ?? null;

  useEffect(() => {
    if (preferredSourceCardId && cards.some((item) => item.id === preferredSourceCardId)) {
      setLeftId(preferredSourceCardId);
      if (rightId === preferredSourceCardId) {
        setRightId(cards.find((item) => item.id !== preferredSourceCardId)?.id ?? "");
      }
    }
  }, [cards, preferredSourceCardId, rightId]);

  async function loadPair() {
    if (!leftId || !rightId || leftId === rightId) return;
    try {
      setLoading(true);
      setError("");
      const [leftPriors, rightPriors] = await Promise.all([
        relationshipApi.listPriors(leftId),
        relationshipApi.listPriors(rightId)
      ]);
      setForward(emptyDraft(leftPriors.items.find((item) => item.target_character_card_id === rightId)));
      setReverse(emptyDraft(rightPriors.items.find((item) => item.target_character_card_id === leftId)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPair();
  }, [leftId, rightId]);

  function patch(direction: "forward" | "reverse", update: Partial<PriorDraft>) {
    const setter = direction === "forward" ? setForward : setReverse;
    setter((current) => ({ ...current, ...update }));
    setMessage("");
  }

  async function generate(direction: "forward" | "reverse") {
    const sourceId = direction === "forward" ? leftId : rightId;
    const targetId = direction === "forward" ? rightId : leftId;
    const draft = direction === "forward" ? forward : reverse;
    if (!sourceId || !targetId) return;
    try {
      setWorking(`generate:${direction}`);
      setError("");
      const generated: RelationshipGeneration = await relationshipApi.generatePrior(sourceId, targetId, {
        relationship_type: draft.relationship_type,
        description: draft.description
      });
      patch(direction, {
        familiarity: generated.familiarity,
        affinity: generated.affinity,
        trust: generated.trust,
        comfort: generated.comfort,
        rationale: generated.rationale
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking("");
    }
  }

  async function save(direction: "forward" | "reverse") {
    const sourceId = direction === "forward" ? leftId : rightId;
    const targetId = direction === "forward" ? rightId : leftId;
    const draft = direction === "forward" ? forward : reverse;
    if (!sourceId || !targetId) return;
    try {
      setWorking(`save:${direction}`);
      setError("");
      await relationshipApi.savePrior(sourceId, targetId, {
        relationship_type: draft.relationship_type,
        description: draft.description,
        familiarity: draft.familiarity,
        affinity: draft.affinity,
        trust: draft.trust,
        comfort: draft.comfort
      });
      setMessage(zh ? "Canonical Relationship 已保存到 Character Card 层。现有 Server lived state 不会被静默覆盖。" : "Canonical Relationship saved at the Character Card layer. Existing Server-lived state was not silently overwritten.");
      await loadPair();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking("");
    }
  }

  if (cards.length < 2) {
    return <p>{zh ? "至少需要两个 Character Card 才能定义 Canonical Relationship。" : "At least two Character Cards are required to define a Canonical Relationship."}</p>;
  }

  return (
    <div className="canonical-relationship-authoring">
      <header>
        <div>
          <span className="tape-label">CHARACTER CARD AUTHORING</span>
          <h3>Relationship Sheet</h3>
          <p>{zh ? "这里编辑角色设定事实与 Starting Dynamics，不直接修改任何 Server 的 lived relationship。两个方向可以不同。" : "Edit canonical facts and Starting Dynamics here. This does not directly mutate any Server-lived relationship, and each direction may differ."}</p>
        </div>
        <div className="canonical-pair-selectors">
          <select value={leftId} onChange={(event) => setLeftId(event.currentTarget.value)}>
            {cards.filter((item) => item.id !== rightId).map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </select>
          <span>↔</span>
          <select value={rightId} onChange={(event) => setRightId(event.currentTarget.value)}>
            {cards.filter((item) => item.id !== leftId).map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </select>
        </div>
      </header>
      {error && <small className="deployment-inline-error">{error}</small>}
      {message && <p className="success-note">{message}</p>}
      {loading ? <p>{zh ? "读取关系设定…" : "Loading relationship authoring state…"}</p> : (
        <div className="canonical-direction-grid">
          <DirectionEditor title={`${left?.display_name ?? "A"} → ${right?.display_name ?? "B"}`} draft={forward} direction="forward" zh={zh} working={working} onPatch={patch} onGenerate={generate} onSave={save} />
          <DirectionEditor title={`${right?.display_name ?? "B"} → ${left?.display_name ?? "A"}`} draft={reverse} direction="reverse" zh={zh} working={working} onPatch={patch} onGenerate={generate} onSave={save} />
        </div>
      )}
    </div>
  );
}

function DirectionEditor({
  title,
  draft,
  direction,
  zh,
  working,
  onPatch,
  onGenerate,
  onSave
}: {
  title: string;
  draft: PriorDraft;
  direction: "forward" | "reverse";
  zh: boolean;
  working: string;
  onPatch: (direction: "forward" | "reverse", update: Partial<PriorDraft>) => void;
  onGenerate: (direction: "forward" | "reverse") => Promise<void>;
  onSave: (direction: "forward" | "reverse") => Promise<void>;
}) {
  const busy = Boolean(working);
  return (
    <article className="canonical-direction-card">
      <h4>{title}</h4>
      <label>
        <span>{zh ? "关系类型" : "Relationship type"}</span>
        <select value={draft.relationship_type} disabled={busy} onChange={(event) => onPatch(direction, { relationship_type: event.currentTarget.value })}>
          {["partners", "siblings", "friends", "rivals", "mentor", "coworkers", "former_friends", "other"].map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>
      <label>
        <span>{zh ? "Canonical 描述" : "Canonical description"}</span>
        <textarea rows={4} value={draft.description} disabled={busy} onChange={(event) => onPatch(direction, { description: event.currentTarget.value })} placeholder={zh ? "只写角色设定中明确存在的关系事实。" : "Only write relationship facts that are explicitly part of the Character setting."} />
      </label>
      <div className="canonical-dimensions">
        {dimensions.map((dimension) => (
          <label key={dimension}>
            <span><strong>{dimensionLabel(dimension, zh)}</strong><small>{score(draft[dimension])}</small></span>
            <input type="range" min={-1} max={1} step={0.05} value={draft[dimension]} disabled={busy} onChange={(event) => onPatch(direction, { [dimension]: Number(event.currentTarget.value) })} />
          </label>
        ))}
      </div>
      {draft.rationale && <p className="relationship-rationale">{draft.rationale}</p>}
      <div className="canonical-actions">
        <button type="button" className="paper-button" disabled={busy} onClick={() => void onGenerate(direction)}>
          {working === `generate:${direction}` ? (zh ? "生成中…" : "Generating…") : (zh ? "✦ AI 建议 Starting Dynamics" : "✦ Generate Starting Dynamics")}
        </button>
        <button type="button" className="ink-button" disabled={busy} onClick={() => void onSave(direction)}>
          {working === `save:${direction}` ? (zh ? "保存中…" : "Saving…") : (zh ? "保存此方向" : "Save direction")}
        </button>
      </div>
    </article>
  );
}
