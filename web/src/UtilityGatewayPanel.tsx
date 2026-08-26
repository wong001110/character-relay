import { useMemo, useState } from "react";

import { CredentialModal } from "./CredentialModal";

export type UtilityProviderId =
  | "openrouter"
  | "groq"
  | "cerebras"
  | "cloudflare"
  | "mistral"
  | "sambanova"
  | "gemini"
  | "custom";

export type UtilityCapability =
  | "semantic_judge"
  | "memory_intelligence"
  | "tool_continuation"
  | "context_compiler"
  | "media_understanding"
  | "structured_summary";

export interface UtilityProviderMember {
  id: string;
  name: string;
  enabled: boolean;
  provider: UtilityProviderId;
  base_url: string;
  model: string;
  capabilities: UtilityCapability[];
  free_only: boolean;
  priority: number;
}

export interface UtilityPaidFallback {
  enabled: boolean;
  provider: "openrouter";
  base_url: string;
  model: string;
  daily_budget_usd: number;
  monthly_budget_usd: number;
}

export interface UtilityGatewayConfig {
  enabled: boolean;
  routing_strategy: "best_available" | "fixed_priority";
  members: UtilityProviderMember[];
  paid_fallback: UtilityPaidFallback;
}

export interface UtilityCredentialStatus {
  member_id: string;
  configured: boolean;
  source: string;
}

export interface UtilityQuotaDimension {
  kind: string;
  remaining: number | null;
  limit: number | null;
  unit: string;
  reset_at: string | null;
  window_seconds: number | null;
  source: string;
  observed_at: string | null;
}

export interface UtilityProviderRuntimeSnapshot {
  member_id: string;
  status: string;
  cooldown_until: string | null;
  last_error: string;
  last_observed_at: string | null;
  observation_source: string;
  quota_dimensions: UtilityQuotaDimension[];
}

export interface UtilityGatewayRuntimeSnapshot {
  enabled: boolean;
  members: UtilityProviderRuntimeSnapshot[];
  paid_fallback_enabled: boolean;
  daily_cost_usd: number;
  monthly_cost_usd: number;
}

interface Props {
  config: UtilityGatewayConfig;
  credentialStatus: UtilityCredentialStatus[];
  runtimeSnapshot: UtilityGatewayRuntimeSnapshot | null;
  zh: boolean;
  onChange: (config: UtilityGatewayConfig) => void;
  onRefreshCredentials: () => Promise<void>;
}

const providers: Array<{
  id: UtilityProviderId;
  label: string;
  baseUrl: string;
  mark: string;
}> = [
  { id: "openrouter", label: "OpenRouter", baseUrl: "https://openrouter.ai/api", mark: "OR" },
  { id: "groq", label: "Groq", baseUrl: "https://api.groq.com/openai", mark: "G" },
  { id: "cerebras", label: "Cerebras", baseUrl: "https://api.cerebras.ai", mark: "C" },
  { id: "cloudflare", label: "Cloudflare Workers AI", baseUrl: "https://api.cloudflare.com/client/v4", mark: "CF" },
  { id: "mistral", label: "Mistral", baseUrl: "https://api.mistral.ai", mark: "M" },
  { id: "sambanova", label: "SambaNova", baseUrl: "https://api.sambanova.ai", mark: "SN" },
  { id: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com", mark: "✦" },
  { id: "custom", label: "Custom", baseUrl: "", mark: "AI" }
];

const capabilityLabels: Record<UtilityCapability, string> = {
  semantic_judge: "Semantic Judge",
  memory_intelligence: "Memory",
  tool_continuation: "Tool Continuation",
  context_compiler: "Context Compiler",
  media_understanding: "Media Understanding",
  structured_summary: "Summary"
};

const capabilityIcons: Record<UtilityCapability, string> = {
  semantic_judge: "⚖",
  memory_intelligence: "✦",
  tool_continuation: "⌁",
  context_compiler: "</>",
  media_understanding: "▧",
  structured_summary: "☷"
};

function newMember(index: number): UtilityProviderMember {
  return {
    id: `provider_${index}`,
    name: `Provider ${index}`,
    enabled: true,
    provider: "openrouter",
    base_url: "https://openrouter.ai/api",
    model: "",
    capabilities: ["semantic_judge"],
    free_only: true,
    priority: 50
  };
}

function providerMeta(provider: UtilityProviderId) {
  return providers.find((item) => item.id === provider) ?? providers[providers.length - 1]!;
}

export function UtilityGatewayPanel({
  config,
  credentialStatus,
  runtimeSnapshot,
  zh,
  onChange,
  onRefreshCredentials
}: Props) {
  const [credentialMember, setCredentialMember] = useState<UtilityProviderMember | null>(null);
  const [expandedMembers, setExpandedMembers] = useState<Set<number>>(() => new Set([0]));
  const statusById = useMemo(
    () => new Map(credentialStatus.map((item) => [item.member_id, item])),
    [credentialStatus]
  );
  const runtimeById = useMemo(
    () => new Map((runtimeSnapshot?.members ?? []).map((item) => [item.member_id, item])),
    [runtimeSnapshot]
  );
  const readyCount = config.members.filter((member) => statusById.get(member.id)?.configured).length;

  function patch(values: Partial<UtilityGatewayConfig>) {
    onChange({ ...config, ...values });
  }

  function patchMember(index: number, values: Partial<UtilityProviderMember>) {
    patch({
      members: config.members.map((member, itemIndex) =>
        itemIndex === index ? { ...member, ...values } : member
      )
    });
  }

  function chooseProvider(index: number, provider: UtilityProviderId) {
    const preset = providers.find((item) => item.id === provider);
    patchMember(index, { provider, base_url: preset?.baseUrl ?? "" });
  }

  function toggleCapability(index: number, capability: UtilityCapability) {
    const member = config.members[index];
    if (!member) return;
    const active = member.capabilities.includes(capability);
    const capabilities = active
      ? member.capabilities.filter((item) => item !== capability)
      : [...member.capabilities, capability];
    if (!capabilities.length) return;
    patchMember(index, { capabilities });
  }

  function toggleExpanded(index: number) {
    setExpandedMembers((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  function addMember() {
    const nextIndex = config.members.length;
    patch({ members: [...config.members, newMember(nextIndex + 1)] });
    setExpandedMembers((current) => new Set([...current, nextIndex]));
  }

  function removeMember(index: number) {
    patch({ members: config.members.filter((_, itemIndex) => itemIndex !== index) });
    setExpandedMembers((current) => {
      const next = new Set<number>();
      for (const value of current) {
        if (value < index) next.add(value);
        if (value > index) next.add(value - 1);
      }
      return next;
    });
  }

  return (
    <section className="runtime-panel utility-gateway-panel">
      <section className="utility-gateway-hero">
        <div className="utility-gateway-hero-main">
          <div>
            <span className="utility-kicker">✦ SYSTEM INTELLIGENCE</span>
            <h3>AI Utility Gateway</h3>
            <p className="section-help">
              {zh
                ? "系统级 AI 统一从这里取用。Free Pool member 永远保持 FREE ONLY，付费兜底只允许 OpenRouter。Capability 可独立分配；没有可用 Provider 时会安全回退到 deterministic / E5 路径。"
                : "System AI is managed here. Free Pool members stay FREE ONLY and paid fallback is OpenRouter-only. Capabilities are assigned independently; consumers with no eligible provider safely fall back to the deterministic / E5 path."}
            </p>
          </div>
          <div className={`utility-gateway-status${config.enabled ? " is-on" : ""}`}>
            <span className="utility-gateway-status-icon">⏻</span>
            <strong>{config.enabled ? "ENABLED" : "OFF"}</strong>
            <small>{config.members.length} {config.members.length === 1 ? "provider" : "providers"}</small>
          </div>
        </div>
        <div className="utility-enable-line">
          <label className="utility-switch-row">
            <span className="utility-switch">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={(event) => patch({ enabled: event.currentTarget.checked })}
              />
              <span className="utility-switch-track" aria-hidden="true" />
            </span>
            <span>{zh ? "启用 Utility Gateway" : "Enable Utility Gateway"}</span>
          </label>
        </div>
      </section>

      <div className="utility-routing-strip">
        <label>
          <span>{zh ? "路由策略" : "Routing strategy"}</span>
          <select
            value={config.routing_strategy}
            onChange={(event) =>
              patch({
                routing_strategy: event.currentTarget.value as UtilityGatewayConfig["routing_strategy"]
              })
            }
          >
            <option value="best_available">Best available</option>
            <option value="fixed_priority">Fixed priority</option>
          </select>
        </label>
      </div>

      <section className="utility-free-pool">
        <header className="utility-section-heading">
          <div className="utility-section-heading-copy">
            <span className="utility-section-icon" aria-hidden="true">♟</span>
            <div>
              <span className="utility-section-eyebrow">FREE POOL</span>
              <h4>{zh ? "免费 Provider" : "Free Providers"}</h4>
            </div>
          </div>
          <span className="utility-section-heading-meta">
            {zh ? `KEY READY ${readyCount} / ${config.members.length}` : `KEY READY ${readyCount} / ${config.members.length}`}
          </span>
        </header>

        <div className="utility-provider-list">
          {config.members.map((member, index) => {
            const credential = statusById.get(member.id);
            const runtime = runtimeById.get(member.id);
            const meta = providerMeta(member.provider);
            const expanded = expandedMembers.has(index);
            return (
              <article className="utility-provider-card" key={`${member.id}-${index}`}>
                <header className="utility-provider-card-head">
                  <div className="utility-provider-identity">
                    <span
                      className={`utility-provider-mark provider-${member.provider}`}
                      aria-hidden="true"
                    >
                      {meta.mark}
                    </span>
                    <div className="utility-provider-name">
                      <span className="utility-member-eyebrow">
                        FREE MEMBER {String(index + 1).padStart(2, "0")}
                      </span>
                      <strong>{member.name || member.id}</strong>
                      <small>{meta.label} · FREE ONLY</small>
                    </div>
                  </div>
                  <div className="utility-provider-statuses">
                    <span className={`utility-state-badge${member.enabled ? " is-enabled" : ""}`}>
                      {member.enabled ? "ENABLED" : "OFF"}
                    </span>
                    <span
                      className={`utility-state-badge${credential?.configured ? " is-ready" : " is-missing"}`}
                    >
                      {credential?.configured ? "KEY READY" : "NO KEY"}
                    </span>
                    <span className={`utility-state-badge utility-runtime-${runtime?.status ?? "unknown"}`}>
                      {(runtime?.status ?? "unknown").replaceAll("_", " ").toUpperCase()}
                    </span>
                    <button
                      type="button"
                      className="utility-collapse-button"
                      aria-label={expanded ? "Collapse provider" : "Expand provider"}
                      aria-expanded={expanded}
                      onClick={() => toggleExpanded(index)}
                    >
                      {expanded ? "⌃" : "⌄"}
                    </button>
                  </div>
                </header>

                {expanded && (
                  <div className="utility-provider-body">
                    <div className="utility-field-grid">
                      <label>
                        {zh ? "名称" : "Name"}
                        <input
                          value={member.name}
                          onChange={(event) => patchMember(index, { name: event.currentTarget.value })}
                        />
                      </label>
                      <label>
                        ID
                        <input
                          value={member.id}
                          onChange={(event) => patchMember(index, { id: event.currentTarget.value })}
                        />
                      </label>
                      <label>
                        Provider
                        <select
                          value={member.provider}
                          onChange={(event) =>
                            chooseProvider(index, event.currentTarget.value as UtilityProviderId)
                          }
                        >
                          {providers.map((provider) => (
                            <option key={provider.id} value={provider.id}>{provider.label}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Model
                        <input
                          value={member.model}
                          onChange={(event) => patchMember(index, { model: event.currentTarget.value })}
                          placeholder="provider model id"
                        />
                      </label>
                      <label className="wide">
                        Base URL
                        <input
                          value={member.base_url}
                          onChange={(event) => patchMember(index, { base_url: event.currentTarget.value })}
                        />
                      </label>
                    </div>

                    <div className="utility-capability-section">
                      <span>Capabilities</span>
                      <div className="utility-capability-grid">
                        {(Object.keys(capabilityLabels) as UtilityCapability[]).map((capability) => {
                          const active = member.capabilities.includes(capability);
                          return (
                            <button
                              type="button"
                              className={`utility-capability-chip${active ? " is-active" : ""}`}
                              aria-pressed={active}
                              key={capability}
                              onClick={() => toggleCapability(index, capability)}
                            >
                              <span className="utility-capability-icon" aria-hidden="true">
                                {active ? "✓" : capabilityIcons[capability]}
                              </span>
                              <span>{capabilityLabels[capability]}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div className="utility-member-bar">
                      <div className="utility-member-controls">
                        <label className="utility-switch-row">
                          <span className="utility-switch">
                            <input
                              type="checkbox"
                              checked={member.enabled}
                              onChange={(event) =>
                                patchMember(index, { enabled: event.currentTarget.checked })
                              }
                            />
                            <span className="utility-switch-track" aria-hidden="true" />
                          </span>
                          <span>{zh ? "启用 member" : "Member enabled"}</span>
                        </label>
                        <label className="utility-priority-field">
                          <span>Priority</span>
                          <input
                            type="number"
                            min="1"
                            max="100"
                            value={member.priority}
                            onChange={(event) =>
                              patchMember(index, { priority: Number(event.currentTarget.value) })
                            }
                          />
                        </label>
                      </div>
                      <div className="utility-provider-actions">
                        <button
                          type="button"
                          className="utility-key-button"
                          onClick={() => setCredentialMember(member)}
                        >
                          🔑 {credential?.configured
                            ? (zh ? "替换 Key" : "Replace key")
                            : (zh ? "配置 Key" : "Configure key")}
                        </button>
                        <button
                          type="button"
                          className="utility-remove-button"
                          onClick={() => removeMember(index)}
                        >
                          ♲ {zh ? "移除 member" : "Remove member"}
                        </button>
                      </div>
                    </div>

                    <section className="utility-runtime-observation">
                      <div className="utility-runtime-observation-head"><strong>{zh ? "Runtime / Quota" : "Runtime / Quota"}</strong><small>{runtime?.last_observed_at ? new Date(runtime.last_observed_at).toLocaleString() : (zh ? "尚未观测" : "Not observed yet")}</small></div>
                      {runtime?.quota_dimensions.length ? (
                        <div className="utility-quota-grid">{runtime.quota_dimensions.map((quota) => <div className="utility-quota-card" key={quota.kind}><span>{quota.kind.replaceAll("_", " ")}</span><strong>{quota.remaining === null ? "Unknown" : `${quota.remaining}${quota.limit === null ? "" : ` / ${quota.limit}`} ${quota.unit}`}</strong><small>{quota.reset_at ? `${zh ? "重置" : "Reset"}: ${new Date(quota.reset_at).toLocaleString()}` : (zh ? "Reset unknown" : "Reset unknown")}</small></div>)}</div>
                      ) : <p className="utility-provider-note">{zh ? "Provider 尚未返回可验证的 quota header；Remaining / Reset 显示 Unknown，不做估算。" : "The provider has not returned authoritative quota headers yet. Remaining / Reset stay Unknown rather than estimated."}</p>}
                      {runtime?.cooldown_until && <p className="utility-runtime-warning">{zh ? "暂时退出 Free Pool，预计可重新 probe：" : "Temporarily out of the Free Pool; probe eligible after: "}{new Date(runtime.cooldown_until).toLocaleString()}</p>}
                      {runtime?.last_error && <p className="utility-runtime-warning">{runtime.last_error}</p>}
                    </section>
                    <p className="utility-provider-note">
                      ⓘ {zh
                        ? "ENABLED 是人工配置；429 / quota 只改变 Runtime health，不会自动关闭 member。冷却或 reset 到期后会自动重新进入 probe。"
                        : "ENABLED is manual configuration. 429/quota only changes Runtime health; it never disables the member. The provider becomes probe eligible automatically after cooldown/reset."}
                    </p>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        <button type="button" className="utility-add-provider" onClick={addMember}>
          ＋ {zh ? "新增 Free Provider" : "Add free provider"}
        </button>
      </section>

      <section className="utility-paid-fallback">
        <header className="utility-paid-head">
          <div className="utility-paid-title">
            <span className="utility-paid-icon" aria-hidden="true">$</span>
            <div>
              <span className="utility-section-eyebrow">PAID FALLBACK</span>
              <h4>{zh ? "仅 OpenRouter" : "OpenRouter only"}</h4>
              <small>
                {zh
                  ? "只有没有任何 eligible FREE member 能处理请求时才会使用。"
                  : "Used only when no eligible FREE member can serve the request."}
              </small>
            </div>
          </div>
          <label className="utility-switch-row">
            <span className="utility-switch">
              <input
                type="checkbox"
                checked={config.paid_fallback.enabled}
                onChange={(event) =>
                  patch({
                    paid_fallback: {
                      ...config.paid_fallback,
                      enabled: event.currentTarget.checked
                    }
                  })
                }
              />
              <span className="utility-switch-track" aria-hidden="true" />
            </span>
            <span>{zh ? "允许付费兜底" : "Allow paid fallback"}</span>
          </label>
        </header>

        <div className="utility-paid-grid">
          <label>
            Model
            <input
              value={config.paid_fallback.model}
              onChange={(event) =>
                patch({
                  paid_fallback: { ...config.paid_fallback, model: event.currentTarget.value }
                })
              }
            />
          </label>
          <label>
            Base URL
            <input
              value={config.paid_fallback.base_url}
              onChange={(event) =>
                patch({
                  paid_fallback: { ...config.paid_fallback, base_url: event.currentTarget.value }
                })
              }
            />
          </label>
          <label>
            {zh ? "每日预算 USD" : "Daily budget USD"}
            <input
              type="number"
              min="0"
              step="0.01"
              value={config.paid_fallback.daily_budget_usd}
              onChange={(event) =>
                patch({
                  paid_fallback: {
                    ...config.paid_fallback,
                    daily_budget_usd: Number(event.currentTarget.value)
                  }
                })
              }
            />
          </label>
          <label>
            {zh ? "每月预算 USD" : "Monthly budget USD"}
            <input
              type="number"
              min="0"
              step="0.1"
              value={config.paid_fallback.monthly_budget_usd}
              onChange={(event) =>
                patch({
                  paid_fallback: {
                    ...config.paid_fallback,
                    monthly_budget_usd: Number(event.currentTarget.value)
                  }
                })
              }
            />
          </label>
        </div>
      </section>

      {credentialMember && (
        <CredentialModal
          utility={{
            memberId: credentialMember.id,
            name: credentialMember.name,
            provider: credentialMember.provider,
            model: credentialMember.model
          }}
          onClose={() => setCredentialMember(null)}
          onConfigured={() => void onRefreshCredentials()}
        />
      )}
    </section>
  );
}
