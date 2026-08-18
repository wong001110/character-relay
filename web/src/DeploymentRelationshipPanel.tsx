import { useEffect, useMemo, useState } from "react";

import {
  relationshipApi,
  type CharacterRelationshipPrior,
  type DeploymentRelationshipCandidate,
  type DeploymentRelationshipCandidates,
  type RelationshipGeneration
} from "./relationshipApi";
import "./deployment-relationships.css";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

interface DraftPrior {
  relationship_type: string;
  description: string;
  familiarity: number;
  affinity: number;
  trust: number;
  comfort: number;
  rationale: string;
}

function draftFrom(candidate: DeploymentRelationshipCandidate): DraftPrior {
  const prior = candidate.canonical_prior;
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

function score(value: number): string {
  return value.toFixed(2);
}

function sliderLabel(value: number, zh: boolean): string {
  if (value >= 0.65) return zh ? "高" : "High";
  if (value >= 0.25) return zh ? "中高" : "Medium-high";
  if (value > -0.25) return zh ? "中性" : "Neutral";
  if (value > -0.65) return zh ? "偏低" : "Low";
  return zh ? "很低" : "Very low";
}

export function DeploymentRelationshipPanel({ deploymentId, disabled = false, zh }: Props) {
  const [data, setData] = useState<DeploymentRelationshipCandidates | null>(null);
  const [drafts, setDrafts] = useState<Record<string, DraftPrior>>({});
  const [expanded, setExpanded] = useState<string>("");
  const [workingKey, setWorkingKey] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const next = await relationshipApi.candidates(deploymentId);
      setData(next);
      setDrafts(
        Object.fromEntries(next.items.map((item) => [item.target_deployment_id, draftFrom(item)]))
      );
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  useEffect(() => {
    setData(null);
    setDrafts({});
    setExpanded("");
    void load();
  }, [deploymentId]);

  const initialized = useMemo(
    () => data?.items.filter((item) => item.dynamic_state !== null).length ?? 0,
    [data]
  );

  function patch(targetDeploymentId: string, update: Partial<DraftPrior>) {
    setDrafts((current) => ({
      ...current,
      [targetDeploymentId]: { ...current[targetDeploymentId], ...update }
    }));
  }

  async function generate(candidate: DeploymentRelationshipCandidate) {
    if (!data) return;
    const current = drafts[candidate.target_deployment_id] ?? draftFrom(candidate);
    setWorkingKey(`generate:${candidate.target_deployment_id}`);
    try {
      const generated: RelationshipGeneration = await relationshipApi.generatePrior(
        data.source_character_card_id,
        candidate.target_character_card_id,
        {
          relationship_type: current.relationship_type,
          description: current.description
        }
      );
      patch(candidate.target_deployment_id, {
        familiarity: generated.familiarity,
        affinity: generated.affinity,
        trust: generated.trust,
        comfort: generated.comfort,
        rationale: generated.rationale
      });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorkingKey("");
    }
  }

  async function save(candidate: DeploymentRelationshipCandidate) {
    if (!data) return;
    const current = drafts[candidate.target_deployment_id] ?? draftFrom(candidate);
    setWorkingKey(`save:${candidate.target_deployment_id}`);
    try {
      await relationshipApi.savePrior(
        data.source_character_card_id,
        candidate.target_character_card_id,
        {
          relationship_type: current.relationship_type,
          description: current.description,
          familiarity: current.familiarity,
          affinity: current.affinity,
          trust: current.trust,
          comfort: current.comfort
        }
      );
      await load();
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorkingKey("");
    }
  }

  async function initialize(candidate: DeploymentRelationshipCandidate) {
    setWorkingKey(`init:${candidate.target_deployment_id}`);
    try {
      await relationshipApi.initialize(deploymentId, candidate.target_deployment_id);
      await load();
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorkingKey("");
    }
  }

  return (
    <section className="deployment-form-wide relationship-sheet">
      <div className="deployment-form-divider relationship-heading">
        <div>
          <strong>{zh ? "角色关系 / Relationship" : "Character relationships"}</strong>
          <span>
            {zh
              ? "Canonical Relationship 是角色卡设定；Starting Dynamics 是可审阅的基线；初始化后，这个 Server 会拥有独立的 lived relationship state。"
              : "Canonical Relationship belongs to the Character Card. Starting Dynamics are reviewable priors; initialization creates independent lived state for this Server."}
          </span>
        </div>
        <small>{data ? `${initialized}/${data.items.length} ${zh ? "已初始化" : "initialized"}` : "…"}</small>
      </div>

      {error && <small className="deployment-inline-error">{error}</small>}
      {!data ? (
        <small>{zh ? "读取同 Server 角色关系…" : "Loading same-server relationships…"}</small>
      ) : data.items.length === 0 ? (
        <small>{zh ? "这个 Server 目前没有其他 Character Deployment。" : "No other Character Deployment exists in this Server yet."}</small>
      ) : (
        <div className="relationship-cards">
          {data.items.map((candidate) => {
            const draft = drafts[candidate.target_deployment_id] ?? draftFrom(candidate);
            const open = expanded === candidate.target_deployment_id;
            const state = candidate.dynamic_state;
            const busy = workingKey.endsWith(candidate.target_deployment_id);
            return (
              <article className="relationship-card" key={candidate.target_deployment_id}>
                <button
                  type="button"
                  className="relationship-card-summary"
                  onClick={() => setExpanded(open ? "" : candidate.target_deployment_id)}
                >
                  <span>
                    <strong>{data.source_display_name} → {candidate.target_display_name}</strong>
                    <small>
                      {candidate.canonical_prior?.relationship_type ?? (zh ? "尚无 Canonical Relationship" : "No canonical relationship")}
                    </small>
                  </span>
                  <span className="relationship-card-status">
                    {state ? (zh ? "Server state 已初始化" : "Server state initialized") : (zh ? "未初始化" : "Not initialized")}
                  </span>
                </button>

                {open && (
                  <div className="relationship-card-body">
                    <div className="relationship-editor-grid">
                      <label>
                        {zh ? "关系类型" : "Relationship type"}
                        <select
                          value={draft.relationship_type}
                          disabled={disabled || busy}
                          onChange={(event) => patch(candidate.target_deployment_id, { relationship_type: event.currentTarget.value })}
                        >
                          {[
                            "partners",
                            "siblings",
                            "friends",
                            "rivals",
                            "mentor",
                            "coworkers",
                            "former_friends",
                            "other"
                          ].map((value) => <option value={value} key={value}>{value}</option>)}
                        </select>
                      </label>
                      <label className="relationship-description">
                        {zh ? "Canonical 描述" : "Canonical description"}
                        <textarea
                          value={draft.description}
                          disabled={disabled || busy}
                          rows={3}
                          onChange={(event) => patch(candidate.target_deployment_id, { description: event.currentTarget.value })}
                          placeholder={zh ? "只写角色设定里明确存在的关系事实。" : "Describe only relationship facts that are part of the Character setting."}
                        />
                      </label>
                    </div>

                    <div className="relationship-dynamics">
                      {(["familiarity", "affinity", "trust", "comfort"] as const).map((dimension) => (
                        <label key={dimension}>
                          <span><strong>{dimension}</strong><small>{sliderLabel(draft[dimension], zh)} · {score(draft[dimension])}</small></span>
                          <input
                            type="range"
                            min={-1}
                            max={1}
                            step={0.05}
                            value={draft[dimension]}
                            disabled={disabled || busy}
                            onChange={(event) => patch(candidate.target_deployment_id, { [dimension]: Number(event.currentTarget.value) })}
                          />
                        </label>
                      ))}
                    </div>

                    {draft.rationale && <p className="relationship-rationale">{draft.rationale}</p>}

                    <div className="relationship-actions">
                      <button type="button" className="paper-button" disabled={disabled || busy} onClick={() => void generate(candidate)}>
                        {workingKey === `generate:${candidate.target_deployment_id}` ? (zh ? "生成中…" : "Generating…") : (zh ? "✦ AI 生成 Starting Dynamics" : "✦ Generate Starting Dynamics")}
                      </button>
                      <button type="button" className="ink-button" disabled={disabled || busy} onClick={() => void save(candidate)}>
                        {zh ? "保存 Canonical Prior" : "Save canonical prior"}
                      </button>
                      <button
                        type="button"
                        className="paper-button"
                        disabled={disabled || busy || !candidate.canonical_prior || Boolean(state)}
                        onClick={() => void initialize(candidate)}
                      >
                        {state ? (zh ? "已初始化" : "Initialized") : (zh ? "Initialize for this Server" : "Initialize for this Server")}
                      </button>
                    </div>

                    {state && (
                      <div className="relationship-current-state">
                        <strong>{zh ? "当前 lived state" : "Current lived state"}</strong>
                        <div>
                          {(["familiarity", "affinity", "trust", "comfort"] as const).map((dimension) => (
                            <span key={dimension}><small>{dimension}</small><b>{score(state[dimension])}</b></span>
                          ))}
                        </div>
                      </div>
                    )}

                    {candidate.impression && (
                      <aside className="relationship-impression">
                        <strong>{zh ? `${data.source_display_name} 如何看待对方` : `How ${data.source_display_name} sees them`}</strong>
                        {candidate.impression.summary && <p>{candidate.impression.summary}</p>}
                        {candidate.impression.observations.length > 0 && (
                          <ul>{candidate.impression.observations.map((item) => <li key={item}>{item}</li>)}</ul>
                        )}
                      </aside>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
