export interface ConversationBurstRuntimeConfig {
  enabled: boolean;
  quiet_window_ms: number;
  max_wait_ms: number;
  max_messages: number;
  max_characters: number;
}

interface Props {
  config: ConversationBurstRuntimeConfig;
  zh: boolean;
  onChange: (config: ConversationBurstRuntimeConfig) => void;
}

const presets = [
  { id: "fast", label: "Fast", quiet: 1500, max: 4000 },
  { id: "balanced", label: "Balanced", quiet: 3000, max: 10000 },
  { id: "patient", label: "Patient", quiet: 5000, max: 15000 }
] as const;

function seconds(value: number): number {
  return Math.round(value / 100) / 10;
}

export function ConversationBurstRuntimePanel({ config, zh, onChange }: Props) {
  const patch = (values: Partial<ConversationBurstRuntimeConfig>) => onChange({ ...config, ...values });
  const activePreset = presets.find((item) => item.quiet === config.quiet_window_ms && item.max === config.max_wait_ms)?.id;
  return (
    <section className="runtime-panel conversation-burst-runtime-panel">
      <div className="utility-section-heading">
        <div className="utility-section-heading-copy">
          <span className="utility-section-icon">◷</span>
          <div><span className="utility-section-eyebrow">CONVERSATION BURST</span><h4>{zh ? "Turn Collector 动态控制" : "Dynamic Turn Collector"}</h4></div>
        </div>
        <span className={`utility-state-badge${config.enabled ? " is-enabled" : ""}`}>{config.enabled ? "ENABLED" : "OFF"}</span>
      </div>
      <p className="section-help">{zh ? "保存后由 Connector 在运行中同步，无需重启。已经打开的 burst 保持创建时的参数；新 burst 使用最新配置。明确角色名、Reply 与 Interaction 仍走即时 fast path。" : "Changes sync into the live Connector without restart. Open bursts keep their original timing snapshot; new bursts use the latest config. Explicit addressing, replies, and interactions remain immediate."}</p>
      <label className="utility-switch-row"><span className="utility-switch"><input type="checkbox" checked={config.enabled} onChange={(event) => patch({ enabled: event.currentTarget.checked })}/><span className="utility-switch-track" /></span><span>{zh ? "启用 Conversation Burst" : "Enable Conversation Burst"}</span></label>
      <div className="conversation-burst-presets">{presets.map((preset) => <button type="button" key={preset.id} className={`paper-button${activePreset === preset.id ? " is-active" : ""}`} onClick={() => patch({ quiet_window_ms: preset.quiet, max_wait_ms: preset.max })}>{preset.label}<small>{seconds(preset.quiet)}s / {seconds(preset.max)}s</small></button>)}</div>
      <div className="utility-field-grid">
        <label>{zh ? "Quiet window（秒）" : "Quiet window (seconds)"}<input type="number" min="0.1" max="10" step="0.1" value={seconds(config.quiet_window_ms)} onChange={(event) => patch({ quiet_window_ms: Math.round(Number(event.currentTarget.value) * 1000) })}/></label>
        <label>{zh ? "Maximum wait（秒）" : "Maximum wait (seconds)"}<input type="number" min="0.5" max="30" step="0.5" value={seconds(config.max_wait_ms)} onChange={(event) => patch({ max_wait_ms: Math.round(Number(event.currentTarget.value) * 1000) })}/></label>
        <label>{zh ? "最多消息" : "Max messages"}<input type="number" min="1" max="20" value={config.max_messages} onChange={(event) => patch({ max_messages: Number(event.currentTarget.value) })}/></label>
        <label>{zh ? "最多字符" : "Max characters"}<input type="number" min="100" max="10000" step="100" value={config.max_characters} onChange={(event) => patch({ max_characters: Number(event.currentTarget.value) })}/></label>
      </div>
      <p className="utility-provider-note">ⓘ {zh ? `当前目标：安静 ${seconds(config.quiet_window_ms)} 秒后判断，最迟 ${seconds(config.max_wait_ms)} 秒强制 flush。` : `Current target: decide after ${seconds(config.quiet_window_ms)}s of quiet, with a hard flush at ${seconds(config.max_wait_ms)}s.`}</p>
    </section>
  );
}
