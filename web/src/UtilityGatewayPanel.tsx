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
  | "topic_intelligence"
  | "memory_intelligence"
  | "knowledge_wiki"
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

interface Props {
  config: UtilityGatewayConfig;
  credentialStatus: UtilityCredentialStatus[];
  zh: boolean;
  onChange: (config: UtilityGatewayConfig) => void;
  onRefreshCredentials: () => Promise<void>;
}

const providers: Array<{ id: UtilityProviderId; label: string; baseUrl: string }> = [
  { id: "openrouter", label: "OpenRouter", baseUrl: "https://openrouter.ai/api" },
  { id: "groq", label: "Groq", baseUrl: "https://api.groq.com/openai" },
  { id: "cerebras", label: "Cerebras", baseUrl: "https://api.cerebras.ai" },
  { id: "cloudflare", label: "Cloudflare Workers AI", baseUrl: "https://api.cloudflare.com/client/v4" },
  { id: "mistral", label: "Mistral", baseUrl: "https://api.mistral.ai" },
  { id: "sambanova", label: "SambaNova", baseUrl: "https://api.sambanova.ai" },
  { id: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com" },
  { id: "custom", label: "Custom", baseUrl: "" }
];

const capabilityLabels: Record<UtilityCapability, string> = {
  semantic_judge: "Semantic Judge",
  topic_intelligence: "Topic",
  memory_intelligence: "Memory",
  knowledge_wiki: "LLM Wiki",
  context_compiler: "Context Compiler",
  media_understanding: "Media Understanding",
  structured_summary: "Summary"
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

export function UtilityGatewayPanel({
  config,
  credentialStatus,
  zh,
  onChange,
  onRefreshCredentials
}: Props) {
  const [credentialMember, setCredentialMember] = useState<UtilityProviderMember | null>(null);
  const statusById = useMemo(
    () => new Map(credentialStatus.map((item) => [item.member_id, item])),
    [credentialStatus]
  );

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

  return (
    <section className="runtime-panel utility-gateway-panel">
      <div className="runtime-heading">
        <div><span>SYSTEM INTELLIGENCE</span><h3>AI Utility Gateway</h3></div>
        <div className={config.enabled ? "runtime-badge ready" : "runtime-badge missing"}>
          {config.enabled ? "ENABLED" : "OFF"}
          <small>{config.members.length} providers</small>
        </div>
      </div>

      <p className="section-help">
        {zh
          ? "系统级 AI 统一从这里取用。Free Pool member 永远是 FREE ONLY；付费兜底只能走 OpenRouter。Phase 1 只建立配置与 Vault，尚未迁移 Topic / Memory / Media 调用。"
          : "System AI is managed here. Free Pool members stay FREE ONLY and paid fallback is OpenRouter-only. Phase 1 establishes configuration and Vault storage only; Topic, Memory, and Media are not migrated yet."}
      </p>

      <div className="utility-gateway-controls">
        <label className="runtime-toggle">
          <input type="checkbox" checked={config.enabled} onChange={(event) => patch({ enabled: event.currentTarget.checked })} />
          {zh ? "启用 Utility Gateway" : "Enable Utility Gateway"}
        </label>
        <label>
          {zh ? "路由策略" : "Routing strategy"}
          <select value={config.routing_strategy} onChange={(event) => patch({ routing_strategy: event.currentTarget.value as UtilityGatewayConfig["routing_strategy"] })}>
            <option value="best_available">Best available</option>
            <option value="fixed_priority">Fixed priority</option>
          </select>
        </label>
      </div>

      <div className="utility-provider-list">
        {config.members.map((member, index) => {
          const credential = statusById.get(member.id);
          return (
            <article className="utility-provider-card" key={`${member.id}-${index}`}>
              <header>
                <div><span>FREE MEMBER {String(index + 1).padStart(2, "0")}</span><strong>{member.name || member.id}</strong></div>
                <div><b>FREE ONLY</b><span className={credential?.configured ? "status-chip is-ready" : "status-chip"}>{credential?.configured ? "KEY ✓" : "NO KEY"}</span></div>
              </header>

              <div className="runtime-provider-grid">
                <label>{zh ? "名称" : "Name"}<input value={member.name} onChange={(event) => patchMember(index, { name: event.currentTarget.value })} /></label>
                <label>ID<input value={member.id} onChange={(event) => patchMember(index, { id: event.currentTarget.value })} /></label>
                <label>Provider<select value={member.provider} onChange={(event) => chooseProvider(index, event.currentTarget.value as UtilityProviderId)}>{providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
                <label>Model<input value={member.model} onChange={(event) => patchMember(index, { model: event.currentTarget.value })} placeholder="provider model id" /></label>
                <label className="wide">Base URL<input value={member.base_url} onChange={(event) => patchMember(index, { base_url: event.currentTarget.value })} /></label>
              </div>

              <div className="utility-capability-grid">
                {(Object.keys(capabilityLabels) as UtilityCapability[]).map((capability) => (
                  <label key={capability}><input type="checkbox" checked={member.capabilities.includes(capability)} onChange={() => toggleCapability(index, capability)} />{capabilityLabels[capability]}</label>
                ))}
              </div>

              <div className="utility-member-options">
                <label className="runtime-toggle"><input type="checkbox" checked={member.enabled} onChange={(event) => patchMember(index, { enabled: event.currentTarget.checked })} />{zh ? "启用 member" : "Member enabled"}</label>
                <label>Priority<input type="number" min="1" max="100" value={member.priority} onChange={(event) => patchMember(index, { priority: Number(event.currentTarget.value) })} /></label>
                <button type="button" className="paper-button" onClick={() => setCredentialMember(member)}>{credential?.configured ? (zh ? "替换 Key" : "Replace key") : (zh ? "配置 Key" : "Configure key")}</button>
              </div>

              <footer>
                <span>{zh ? "Quota / Health 会在 Phase 2 接入" : "Quota / Health arrives in Phase 2"}</span>
                <button type="button" className="key-group-delete-link" onClick={() => patch({ members: config.members.filter((_, itemIndex) => itemIndex !== index) })}>{zh ? "移除 member" : "Remove member"}</button>
              </footer>
            </article>
          );
        })}
      </div>

      <button type="button" className="paper-button utility-add-provider" onClick={() => patch({ members: [...config.members, newMember(config.members.length + 1)] })}>＋ {zh ? "新增 Free Provider" : "Add free provider"}</button>

      <section className="utility-paid-fallback">
        <header>
          <div><span>PAID FALLBACK</span><strong>OpenRouter only</strong></div>
          <label className="runtime-toggle"><input type="checkbox" checked={config.paid_fallback.enabled} onChange={(event) => patch({ paid_fallback: { ...config.paid_fallback, enabled: event.currentTarget.checked } })} />{zh ? "允许付费兜底" : "Allow paid fallback"}</label>
        </header>
        <div className="runtime-provider-grid">
          <label>Model<input value={config.paid_fallback.model} onChange={(event) => patch({ paid_fallback: { ...config.paid_fallback, model: event.currentTarget.value } })} /></label>
          <label>{zh ? "每日预算 USD" : "Daily budget USD"}<input type="number" min="0" step="0.01" value={config.paid_fallback.daily_budget_usd} onChange={(event) => patch({ paid_fallback: { ...config.paid_fallback, daily_budget_usd: Number(event.currentTarget.value) } })} /></label>
          <label>{zh ? "每月预算 USD" : "Monthly budget USD"}<input type="number" min="0" step="0.1" value={config.paid_fallback.monthly_budget_usd} onChange={(event) => patch({ paid_fallback: { ...config.paid_fallback, monthly_budget_usd: Number(event.currentTarget.value) } })} /></label>
          <label className="wide">Base URL<input value={config.paid_fallback.base_url} onChange={(event) => patch({ paid_fallback: { ...config.paid_fallback, base_url: event.currentTarget.value } })} /></label>
        </div>
      </section>

      {credentialMember && (
        <CredentialModal
          utility={{ memberId: credentialMember.id, name: credentialMember.name, provider: credentialMember.provider, model: credentialMember.model }}
          onClose={() => setCredentialMember(null)}
          onConfigured={() => void onRefreshCredentials()}
        />
      )}
    </section>
  );
}
