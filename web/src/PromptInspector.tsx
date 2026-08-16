import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import {
  Button,
  PaperTab,
  Select,
  Spinner,
  Stamp,
  StickyLabel,
  Toast
} from "./components/ui";
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

type PromptLayer = "raw" | "compiled";

const formats: Array<{ value: PromptExportFormat; label: string }> = [
  { value: "raw", label: "Raw Prompt (.raw.txt)" },
  { value: "text", label: "Compiled Prompt (.compiled.txt)" },
  { value: "markdown", label: "Pipeline Markdown (.md)" },
  { value: "json", label: "Full metadata JSON (.json)" },
  { value: "openai", label: "OpenAI messages JSON (.openai.json)" }
];

const copy = {
  en: {
    title: "Prompt Pipeline",
    subtitle:
      "Compare the creator-authored Raw Prompt with the exact Compiled Character Prompt used as the runtime System Message.",
    close: "Close",
    loading: "Compiling the current Character Card…",
    copy: "Copy current layer",
    copied: "Copied",
    export: "Export format",
    download: "Download",
    provider: "Provider",
    model: "Model",
    temperature: "Temperature",
    version: "Raw Prompt version",
    configHash: "Raw config hash",
    compiler: "Compiler",
    compiledHash: "Compiled prompt hash",
    raw: "Raw Prompt",
    compiled: "Compiled Character Prompt",
    rawHelp: "The exact System Prompt entered by the creator. It remains editable source material.",
    compiledHelp:
      "The runtime System Message after Character Card identity, traits, tone, memory boundary, and forbidden behaviors are compiled in.",
    sourceNote: "Creator source",
    runtimeNote: "Runtime system message",
    manuscript: "Prompt manuscript",
    unavailable: "This Character Card does not have a Provider-backed System Prompt."
  },
  "zh-CN": {
    title: "Prompt 编译管线",
    subtitle: "对比创作者输入的 Raw Prompt，以及 Runtime 实际使用的 Compiled Character Prompt。",
    close: "关闭",
    loading: "正在编译当前角色卡…",
    copy: "复制当前层",
    copied: "已复制",
    export: "导出格式",
    download: "下载",
    provider: "Provider",
    model: "Model",
    temperature: "Temperature",
    version: "Raw Prompt 版本",
    configHash: "Raw 配置 Hash",
    compiler: "Compiler",
    compiledHash: "Compiled Prompt Hash",
    raw: "Raw Prompt",
    compiled: "Compiled Character Prompt",
    rawHelp: "创作者直接输入的原始 System Prompt，作为可编辑的源内容保留。",
    compiledHelp:
      "把角色身份、性格、语气、记忆边界与禁止行为编译进去后，Runtime 实际使用的完整 System Message。",
    sourceNote: "创作者原稿",
    runtimeNote: "Runtime System Message",
    manuscript: "Prompt 原稿",
    unavailable: "这个角色卡没有使用 Provider System Prompt。"
  }
} as const;

export function PromptInspector({ card, onClose }: Props) {
  const { language } = useI18n();
  const c = copy[language];
  const [prompt, setPrompt] = useState<CharacterPromptView | null>(null);
  const [layer, setLayer] = useState<PromptLayer>("compiled");
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
    return () => {
      active = false;
    };
  }, [card.id, c.unavailable]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const currentPrompt = useMemo(() => {
    if (!prompt) return "";
    return layer === "raw"
      ? prompt.raw_system_prompt
      : prompt.compiled_system_prompt;
  }, [layer, prompt]);

  async function copyPrompt() {
    if (!currentPrompt) return;
    await navigator.clipboard.writeText(currentPrompt);
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
            <p className="tape-label">CHARACTER FILE / RUNTIME INSERT</p>
            <StickyLabel variant="link">{c.manuscript}</StickyLabel>
            <h2 id="prompt-inspector-title">
              {card.display_name} · {c.title}
            </h2>
            <p>{c.subtitle}</p>
          </div>
          <Button type="button" variant="secondary" onClick={onClose}>
            {c.close}
          </Button>
        </header>

        {loading && (
          <div className="prompt-loading-sheet" role="status" aria-live="polite">
            <Spinner label={c.loading} />
            <p>{c.loading}</p>
          </div>
        )}
        {error && <Toast tone="danger" className="prompt-status">{error}</Toast>}

        {prompt && (
          <>
            <dl className="prompt-meta">
              <div>
                <dt>{c.provider}</dt>
                <dd>{prompt.provider}</dd>
              </div>
              <div>
                <dt>{c.model}</dt>
                <dd>{prompt.model}</dd>
              </div>
              <div>
                <dt>{c.temperature}</dt>
                <dd>{prompt.temperature}</dd>
              </div>
              <div>
                <dt>{c.version}</dt>
                <dd>
                  {prompt.prompt_version_label ?? `v${prompt.prompt_version ?? "—"}`}
                </dd>
              </div>
              <div className="prompt-meta-wide">
                <dt>{c.configHash}</dt>
                <dd>{prompt.config_hash ?? "—"}</dd>
              </div>
              <div className="prompt-meta-wide prompt-compiled-meta">
                <span>
                  <dt>{c.compiler}</dt>
                  <dd>{prompt.compiler_version}</dd>
                </span>
                <span>
                  <dt>{c.compiledHash}</dt>
                  <dd>{prompt.compiled_prompt_hash}</dd>
                </span>
              </div>
            </dl>

            <div className="prompt-layer-tabs" role="tablist" aria-label={c.title}>
              <PaperTab
                tone="yellow"
                active={layer === "raw"}
                onClick={() => setLayer("raw")}
              >
                <strong>{c.raw}</strong>
                <span>{c.rawHelp}</span>
              </PaperTab>
              <span className="prompt-pipeline-arrow" aria-hidden="true">→</span>
              <PaperTab
                tone="blue"
                active={layer === "compiled"}
                onClick={() => setLayer("compiled")}
              >
                <strong>{c.compiled}</strong>
                <span>{c.compiledHelp}</span>
              </PaperTab>
            </div>

            <div className="prompt-layer-state" aria-label={layer === "raw" ? c.raw : c.compiled}>
              <Stamp variant={layer === "raw" ? "accent" : "info"}>
                {layer === "raw" ? "SOURCE" : "COMPILED"}
              </Stamp>
              <StickyLabel variant={layer === "raw" ? "warning" : "link"}>
                {layer === "raw" ? c.sourceNote : c.runtimeNote}
              </StickyLabel>
              {layer === "compiled" && (
                <StickyLabel variant="neutral">{prompt.compiler_version}</StickyLabel>
              )}
            </div>

            <div className="prompt-source-heading">
              <div>
                <p className="prompt-layer-kicker">
                  {layer === "raw" ? "SOURCE MANUSCRIPT" : "RUNTIME SYSTEM MESSAGE"}
                </p>
                <h3>{layer === "raw" ? c.raw : c.compiled}</h3>
              </div>
              <Button type="button" variant="secondary" size="sm" onClick={() => void copyPrompt()}>
                {copied ? c.copied : c.copy}
              </Button>
            </div>
            <pre className="prompt-source">
              <code>{currentPrompt}</code>
            </pre>

            <div className="prompt-export-bar">
              <label>
                <span>{c.export}</span>
                <Select
                  value={format}
                  onChange={(event) =>
                    setFormat(event.currentTarget.value as PromptExportFormat)
                  }
                >
                  {formats.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </label>
              <Button type="button" variant="primary" onClick={download}>
                {c.download}
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
