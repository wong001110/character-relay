import type { AdminRuntimeConfig, AdminRuntimeView, ProviderId } from "./api";
import { getProviderPreset, providerPresets } from "./providerPresets";

export interface SemanticJudgeEndpointConfig {
  provider: ProviderId;
  base_url: string;
  model: string;
}

export interface SemanticRoutingJudgeConfig {
  enabled: boolean;
  rag_enabled: boolean;
  primary: SemanticJudgeEndpointConfig;
  availability_fallback: SemanticJudgeEndpointConfig;
  quality_escalation: SemanticJudgeEndpointConfig;
  system_prompt: string;
  rag_off_threshold: number;
  rag_on_threshold: number;
  confidence_threshold: number;
  timeout_seconds: number;
  max_input_chars: number;
  max_output_tokens: number;
}

interface ExtendedStatus {
  enabled: boolean;
  configured: boolean;
  provider: string;
  model: string;
  credential_source: string;
}

export type SemanticRoutingAdminView = AdminRuntimeView & {
  config: AdminRuntimeConfig & { semantic_routing: SemanticRoutingJudgeConfig };
  status: AdminRuntimeView["status"] & {
    semantic_primary: ExtendedStatus;
    semantic_availability: ExtendedStatus;
    semantic_quality: ExtendedStatus;
  };
};

interface Props {
  view: SemanticRoutingAdminView;
  zh: boolean;
  onChange: (config: SemanticRoutingJudgeConfig) => void;
}

function EndpointEditor({ title, note, endpoint, status, onChange }: {
  title: string;
  note: string;
  endpoint: SemanticJudgeEndpointConfig;
  status: ExtendedStatus;
  onChange: (next: SemanticJudgeEndpointConfig) => void;
}) {
  function choose(provider: ProviderId) {
    const preset = getProviderPreset(provider);
    onChange({ provider, base_url: preset.baseUrl, model: preset.defaultModel });
  }

  return (
    <section className="semantic-routing-tier">
      <header>
        <div><strong>{title}</strong><small>{note}</small></div>
        <span className={status.configured ? "status-chip is-ready" : "status-chip"}>
          {status.configured ? "READY" : "MISSING"} · {status.credential_source}
        </span>
      </header>
      <div className="runtime-provider-grid">
        <label>
          Provider
          <select value={endpoint.provider} onChange={(event) => choose(event.currentTarget.value as ProviderId)}>
            {providerPresets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label>
          Model
          <input value={endpoint.model} onChange={(event) => onChange({ ...endpoint, model: event.currentTarget.value })} />
        </label>
        <label className="wide">
          Base URL
          <input value={endpoint.base_url} onChange={(event) => onChange({ ...endpoint, base_url: event.currentTarget.value })} />
        </label>
      </div>
    </section>
  );
}

export function SemanticRoutingJudgePanel({ view, zh, onChange }: Props) {
  const config = view.config.semantic_routing;
  function patch(values: Partial<SemanticRoutingJudgeConfig>) {
    onChange({ ...config, ...values });
  }

  return (
    <section className="runtime-panel semantic-routing-runtime-panel">
      <div className="runtime-heading">
        <div><span>SEMANTIC RUNTIME</span><h3>Discord Routing Judge</h3></div>
        <div className={config.enabled && view.status.semantic_primary.configured ? "runtime-badge ready" : "runtime-badge missing"}>
          {config.enabled && view.status.semantic_primary.configured ? "READY" : "OFF / MISSING"}
          <small>RAG ambiguity</small>
        </div>
      </div>
      <p className="section-help">
        {zh
          ? "只处理 E5 无法明确决定的灰区。明确相关／无关仍由 deterministic gate 直接处理；Judge 全部失败时退回 deterministic 决策。三个 tier 目前共享上方 Semantic Judge 的加密 Provider Key。"
          : "Only ambiguous E5 cases invoke this Judge. Clear decisions remain deterministic, and complete Judge failure falls back to the deterministic gate. The three tiers currently share the encrypted Semantic Judge provider key above."}
      </p>
      <div className="semantic-routing-toggle-row">
        <label className="runtime-toggle"><input type="checkbox" checked={config.enabled} onChange={(event) => patch({ enabled: event.currentTarget.checked })} />{zh ? "启用 Routing Judge" : "Enable Routing Judge"}</label>
        <label className="runtime-toggle"><input type="checkbox" checked={config.rag_enabled} onChange={(event) => patch({ rag_enabled: event.currentTarget.checked })} />RAG ambiguity</label>
      </div>
      <div className="semantic-routing-tiers">
        <EndpointEditor title="01 · PRIMARY" note={zh ? "灰区默认先问；优先免费模型。" : "First choice for ambiguous turns."} endpoint={config.primary} status={view.status.semantic_primary} onChange={(primary) => patch({ primary })} />
        <EndpointEditor title="02 · AVAILABILITY FALLBACK" note={zh ? "429、timeout、provider error 时使用。" : "Used for 429, timeout, or provider failure."} endpoint={config.availability_fallback} status={view.status.semantic_availability} onChange={(availability_fallback) => patch({ availability_fallback })} />
        <EndpointEditor title="03 · QUALITY ESCALATION" note={zh ? "低置信度或无效 JSON 时升级。" : "Used for low confidence or invalid JSON."} endpoint={config.quality_escalation} status={view.status.semantic_quality} onChange={(quality_escalation) => patch({ quality_escalation })} />
      </div>
      <div className="semantic-routing-thresholds">
        <label>{zh ? "E5 直接 OFF" : "E5 direct OFF"}<input type="number" min="-1" max="1" step="0.01" value={config.rag_off_threshold} onChange={(event) => patch({ rag_off_threshold: Number(event.currentTarget.value) })} /><small>≤ score</small></label>
        <label>{zh ? "E5 直接 ON" : "E5 direct ON"}<input type="number" min="-1" max="1" step="0.01" value={config.rag_on_threshold} onChange={(event) => patch({ rag_on_threshold: Number(event.currentTarget.value) })} /><small>≥ score</small></label>
        <label>{zh ? "Judge 置信度" : "Judge confidence"}<input type="number" min="0" max="1" step="0.01" value={config.confidence_threshold} onChange={(event) => patch({ confidence_threshold: Number(event.currentTarget.value) })} /><small>{zh ? "低于此值 → quality escalation" : "Below → quality escalation"}</small></label>
        <label>Timeout<input type="number" min="0.5" max="20" step="0.5" value={config.timeout_seconds} onChange={(event) => patch({ timeout_seconds: Number(event.currentTarget.value) })} /><small>seconds / attempt</small></label>
      </div>
      <details className="semantic-routing-advanced">
        <summary>Advanced Judge contract</summary>
        <label className="wide">System Prompt<textarea rows={5} value={config.system_prompt} onChange={(event) => patch({ system_prompt: event.currentTarget.value })} /></label>
        <div className="runtime-number-grid">
          <label>Max input chars<input type="number" min="500" max="16000" step="100" value={config.max_input_chars} onChange={(event) => patch({ max_input_chars: Number(event.currentTarget.value) })} /></label>
          <label>Max output tokens<input type="number" min="24" max="256" value={config.max_output_tokens} onChange={(event) => patch({ max_output_tokens: Number(event.currentTarget.value) })} /></label>
        </div>
      </details>
    </section>
  );
}
