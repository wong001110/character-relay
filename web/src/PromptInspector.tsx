import { useEffect, useState } from "react";

import type { CharacterCard } from "./api";
import { useI18n } from "./i18n";
import {
  promptApi,
  type CharacterPromptView,
  type PromptExportFormat
} from "./promptApi";
import "./prompt-inspector.css";

interface Props {
  card: CharacterCard;
  onClose: () => void;
}

const formats: Array<{ value: PromptExportFormat; label: string }> = [
  { value: "text", label: "Plain text (.txt)" },
  { value: "markdown", label: "Markdown (.md)" },
  { value: "json", label: "Full metadata JSON (.json)" },
  { value: "openai", label: "OpenAI messages JSON (.openai.json)" }
];

const copy = {
  en: {
    title: "Runtime Prompt",
    subtitle: "The exact System Message currently sent to the model runtime.",
    close: "Close",
    loading: "Reading the current Target configuration…",
    copy: "Copy prompt",
    copied: "Copied",
    export: "Export format",
    download: "Download",
    provider: "Provider",
    model: "Model",
    temperature: "Temperature",
    version: "Active version",
    hash: "Config hash",
    exact: "Exact System Message",
    unavailable: "This Character Card does not have a Provider-backed System Prompt."
  },
  "zh-CN": {
    title: "Runtime 真实 Prompt",
    subtitle: "当前实际发送给模型 Runtime 的完整 System Message。",
    close: "关闭",
    loading: "正在读取当前 Target 配置…",
    copy: "复制 Prompt",
    copied: "已复制",
    export: "导出格式",
    download: "下载",
    provider: "Provider",
    model: "Model",
    temperature: "Temperature",
    version: "当前版本",
    hash: "配置 Hash",
    exact: "完整 System Message",
    unavailable: "这个角色卡没有使用 Provider System Prompt。"
  }
} as const;

export function PromptInspector({ card, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [prompt, setPrompt] = useState<CharacterPromptView | null>(null);
  const [format, setFormat] = useState<PromptExportFormat>("markdown");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const view = await promptApi.inspect(card.id);
        if (active) setPrompt(view);
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : c.unavailable);
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [card.id, c.unavailable]);

  async function copyPrompt() {
    if (!prompt) return;
    await navigator.clipboard.writeText(prompt.system_prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  function download() {
    if (!prompt) return;
    const link = document.createElement("a");
    link.href = promptApi.exportUrl(card.id, format);
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <div className="prompt-inspector-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="prompt-inspector paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-inspector-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="prompt-inspector-header">
          <div>
            <p className="tape-label">Echo Masque · Runtime</p>
            <h2 id="prompt-inspector-title">{card.display_name} · {c.title}</h2>
            <p>{c.subtitle}</p>
          </div>
          <button type="button" className="paper-button" onClick={onClose}>{c.close}</button>
        </header>

        {loading && <p className="prompt-status">{c.loading}</p>}
        {error && <p className="error-note prompt-status">{error}</p>}

        {prompt && (
          <>
            <dl className="prompt-meta">
              <div><dt>{c.provider}</dt><dd>{prompt.provider}</dd></div>
              <div><dt>{c.model}</dt><dd>{prompt.model}</dd></div>
              <div><dt>{c.temperature}</dt><dd>{prompt.temperature}</dd></div>
              <div><dt>{c.version}</dt><dd>{prompt.prompt_version_label ?? `v${prompt.prompt_version ?? "—"}`}</dd></div>
              <div className="prompt-meta-wide"><dt>{c.hash}</dt><dd>{prompt.config_hash ?? "—"}</dd></div>
            </dl>

            <div className="prompt-source-heading">
              <h3>{c.exact}</h3>
              <button type="button" className="paper-button" onClick={() => void copyPrompt()}>
                {copied ? c.copied : c.copy}
              </button>
            </div>
            <pre className="prompt-source"><code>{prompt.system_prompt}</code></pre>

            <div className="prompt-export-bar">
              <label>
                <span>{c.export}</span>
                <select
                  value={format}
                  onChange={(event) => setFormat(event.currentTarget.value as PromptExportFormat)}
                >
                  {formats.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="ink-button" onClick={download}>{c.download}</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
