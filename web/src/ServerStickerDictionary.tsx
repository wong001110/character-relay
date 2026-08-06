import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent
} from "react";

import type { DiscordServerProfile } from "./deploymentApi";
import {
  interactionApi,
  type ExpressionAction,
  type ExpressionRun,
  type ExpressionRunDetail,
  type ExpressionSemantic,
  type ExpressionSemanticCreate
} from "./interactionApi";
import {
  NotebookField,
  NotebookInput,
  NotebookTextarea,
  PaperModal
} from "./NotebookUI";

interface Props {
  profile: DiscordServerProfile;
  demoMode: boolean;
  zh: boolean;
  onError: (message: string) => void;
}

type DictionaryTab = "emoji" | "sticker" | "history";
type AllowedExpressionAction = Exclude<ExpressionAction, "none">;

interface ImportPreviewItem {
  key: string;
  resource: ExpressionSemantic | null;
  payload: ExpressionSemanticCreate | null;
  errors: string[];
}

interface ImportPreview {
  fileName: string;
  items: ImportPreviewItem[];
}

const ALLOWED_ACTIONS: AllowedExpressionAction[] = ["inline", "reaction", "sticker"];

function splitLines(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(/[,，\n]/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return typeof value === "string" ? splitLines(value) : [];
}

function actions(value: unknown, fallback: AllowedExpressionAction[]): AllowedExpressionAction[] {
  if (!Array.isArray(value)) return fallback;
  const result = value.filter(
    (item): item is AllowedExpressionAction =>
      typeof item === "string" && ALLOWED_ACTIONS.includes(item as AllowedExpressionAction)
  );
  return result.length ? [...new Set(result)] : fallback;
}

function expressionPayload(
  resource: ExpressionSemantic,
  overrides: Partial<ExpressionSemanticCreate> = {}
): ExpressionSemanticCreate {
  return {
    connection_id: resource.connection_id,
    guild_id: resource.guild_id,
    resource_type: resource.resource_type,
    resource_id: resource.resource_id,
    name: resource.name,
    description: resource.description,
    tags: resource.tags,
    format_type: resource.format_type,
    asset_url: resource.asset_url,
    animated: resource.animated,
    available: resource.available,
    enabled: resource.enabled,
    semantic_intent: resource.semantic_intent,
    semantic_emotion: resource.semantic_emotion,
    semantic_description: resource.semantic_description,
    aliases: resource.aliases,
    situations: resource.situations,
    avoid_when: resource.avoid_when,
    allowed_actions: resource.allowed_actions,
    ...overrides
  };
}

export function ServerStickerDictionary({ profile, demoMode, zh, onError }: Props) {
  const [resources, setResources] = useState<ExpressionSemantic[]>([]);
  const [runs, setRuns] = useState<ExpressionRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ExpressionRunDetail | null>(null);
  const [editing, setEditing] = useState<ExpressionSemantic | null>(null);
  const [tab, setTab] = useState<DictionaryTab>("emoji");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [assistantWorking, setAssistantWorking] = useState(false);
  const [assistantContext, setAssistantContext] = useState("");
  const [assistantMessage, setAssistantMessage] = useState<string | null>(null);
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const editorRef = useRef<HTMLFormElement | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  async function load() {
    try {
      setLoading(true);
      const [nextResources, nextRuns] = await Promise.all([
        interactionApi.listExpressions(profile.connection_id, profile.guild_id),
        interactionApi.listExpressionRuns(profile.connection_id, profile.guild_id)
      ]);
      setResources(nextResources);
      setRuns(nextRuns);
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setEditing(null);
    setSelectedRun(null);
    setImportPreview(null);
    setAssistantContext("");
    setAssistantMessage(null);
    setNotice(null);
    void load();
  }, [profile.connection_id, profile.guild_id]);

  useEffect(() => {
    if (!editing) return;
    const timer = window.setTimeout(() => {
      editorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [editing?.id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const allowedActions = ALLOWED_ACTIONS.filter(
      (action) => data.get(`allow_${action}`) === "on"
    );
    try {
      setWorking(true);
      const saved = await interactionApi.saveExpression(
        expressionPayload(editing, {
          enabled: data.get("enabled") === "on",
          semantic_intent: String(data.get("semantic_intent") ?? "").trim(),
          semantic_emotion: String(data.get("semantic_emotion") ?? "").trim(),
          semantic_description: String(data.get("semantic_description") ?? "").trim(),
          aliases: splitLines(data.get("aliases")),
          situations: splitLines(data.get("situations")),
          avoid_when: splitLines(data.get("avoid_when")),
          allowed_actions: allowedActions.length
            ? allowedActions
            : editing.resource_type === "emoji"
              ? ["inline", "reaction"]
              : ["sticker"]
        })
      );
      setResources((current) =>
        current.map((item) => (item.id === saved.id ? saved : item))
      );
      setEditing(null);
      setAssistantContext("");
      setAssistantMessage(null);
      setNotice(zh ? `已保存 ${saved.name} 的定义。` : `Saved the definition for ${saved.name}.`);
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function openRun(run: ExpressionRun) {
    try {
      setWorking(true);
      setSelectedRun(await interactionApi.getExpressionRun(run.id));
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function selectTab(nextTab: DictionaryTab) {
    setEditing(null);
    setSelectedRun(null);
    setAssistantContext("");
    setAssistantMessage(null);
    setTab(nextTab);
  }

  function toggleEditor(item: ExpressionSemantic) {
    setEditing((current) => (current?.id === item.id ? null : item));
    setAssistantContext("");
    setAssistantMessage(null);
  }

  function setEditorValue(name: string, value: string) {
    const element = editorRef.current?.elements.namedItem(name);
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      element.value = value;
    }
  }

  async function generateSuggestion(item: ExpressionSemantic) {
    const context = assistantContext.trim();
    if (context.length < 3) {
      setAssistantMessage(
        zh ? "先描述这个表情通常在什么场景使用。" : "Describe when this expression is normally used first."
      );
      return;
    }
    try {
      setAssistantWorking(true);
      setAssistantMessage(null);
      const suggestion = await interactionApi.suggestExpression({
        resource_type: item.resource_type,
        resource_id: item.resource_id,
        name: item.name,
        description: item.description,
        tags: item.tags,
        animated: item.animated,
        asset_url: item.asset_url,
        usage_context: context,
        language: zh ? "zh-CN" : "en"
      });
      setEditorValue("semantic_intent", suggestion.semantic_intent);
      setEditorValue("semantic_emotion", suggestion.semantic_emotion);
      setEditorValue("semantic_description", suggestion.semantic_description);
      setEditorValue("aliases", suggestion.aliases.join("\n"));
      setEditorValue("situations", suggestion.situations.join("\n"));
      setEditorValue("avoid_when", suggestion.avoid_when.join("\n"));
      setAssistantMessage(
        zh
          ? `已使用 ${suggestion.provider_model} 填入草稿，请审核后再保存。`
          : `Drafted with ${suggestion.provider_model}. Review it before saving.`
      );
      onError("");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setAssistantMessage(message);
      onError(message);
    } finally {
      setAssistantWorking(false);
    }
  }

  function exportJson() {
    const document = {
      version: 2,
      kind: "character-relay-expression-dictionary",
      agent_guidance: {
        purpose:
          "Review each Discord Emoji or Sticker visually, then draft semantic fields for Character Relay.",
        visual_analysis:
          "Open each asset_url with a vision-capable tool before deciding its meaning. Animated assets may require viewing the full animation.",
        editable_fields: [
          "enabled",
          "semantic_intent",
          "semantic_emotion",
          "semantic_description",
          "aliases",
          "situations",
          "avoid_when",
          "allowed_actions"
        ],
        readonly_fields: [
          "resource_key",
          "resource_type",
          "resource_id",
          "name",
          "description",
          "tags",
          "asset_url",
          "format_type",
          "animated",
          "available"
        ],
        uncertainty_rule:
          "When the visual meaning is unclear, keep the semantic fields empty or mark the uncertainty for human review. Do not infer meaning from the filename alone."
      },
      server: {
        profile_id: profile.id,
        guild_id: profile.guild_id,
        guild_name: profile.guild_name,
        workspace_name: profile.name
      },
      exported_at: new Date().toISOString(),
      expressions: resources.map((item) => ({
        resource_key: item.resource_key,
        resource_type: item.resource_type,
        resource_id: item.resource_id,
        name: item.name,
        description: item.description,
        tags: item.tags,
        asset_url: item.asset_url,
        format_type: item.format_type,
        animated: item.animated,
        available: item.available,
        enabled: item.enabled,
        semantic_intent: item.semantic_intent,
        semantic_emotion: item.semantic_emotion,
        semantic_description: item.semantic_description,
        aliases: item.aliases,
        situations: item.situations,
        avoid_when: item.avoid_when,
        allowed_actions: item.allowed_actions
      }))
    };
    const blob = new Blob([JSON.stringify(document, null, 2)], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement("a");
    const safeName = profile.guild_name.replace(/[^a-z0-9_-]+/giu, "-").replace(/^-+|-+$/g, "");
    link.href = url;
    link.download = `character-relay-${safeName || profile.guild_id}-expressions.json`;
    link.click();
    URL.revokeObjectURL(url);
    setNotice(
      zh
        ? "已导出包含 Emoji／Sticker 图片链接与 AI Agent 指引的 Expression JSON。"
        : "Exported Expression JSON with Emoji/Sticker image links and AI-agent guidance."
    );
  }

  async function readImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const root = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
      const entries = Array.isArray(parsed)
        ? parsed
        : root && Array.isArray(root.expressions)
          ? root.expressions
          : null;
      if (!entries) throw new Error(zh ? "JSON 必须是数组，或包含 expressions 数组。" : "JSON must be an array or contain an expressions array.");

      const resourceMap = new Map(resources.map((item) => [item.resource_key, item]));
      const previewItems: ImportPreviewItem[] = entries.map((entry, index) => {
        if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
          return {
            key: `row-${index + 1}`,
            resource: null,
            payload: null,
            errors: [zh ? "不是有效的 Expression 对象。" : "Not a valid Expression object."]
          };
        }
        const value = entry as Record<string, unknown>;
        const resourceType = stringValue(value.resource_type);
        const resourceId = stringValue(value.resource_id);
        const key = stringValue(value.resource_key) ||
          (resourceType && resourceId ? `${resourceType}:${resourceId}` : `row-${index + 1}`);
        const resource = resourceMap.get(key) ?? null;
        const errors: string[] = [];
        if (!resource) {
          errors.push(
            zh
              ? "当前 Server 没有匹配的已同步资源；不会按名称猜测。"
              : "No synchronized resource matches this Server; names are not guessed."
          );
        }
        const meaning = stringValue(value.semantic_description);
        if (!meaning) {
          errors.push(zh ? "缺少 semantic_description。" : "semantic_description is required.");
        }
        const fallbackActions = resource?.allowed_actions ?? [];
        const payload = resource && !errors.length
          ? expressionPayload(resource, {
              enabled: typeof value.enabled === "boolean" ? value.enabled : resource.enabled,
              semantic_intent: stringValue(value.semantic_intent),
              semantic_emotion: stringValue(value.semantic_emotion),
              semantic_description: meaning,
              aliases: stringList(value.aliases),
              situations: stringList(value.situations ?? value.use_when),
              avoid_when: stringList(value.avoid_when),
              allowed_actions: actions(value.allowed_actions, fallbackActions)
            })
          : null;
        return { key, resource, payload, errors };
      });
      setImportPreview({ fileName: file.name, items: previewItems });
      setNotice(null);
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function confirmImport() {
    if (!importPreview) return;
    const valid = importPreview.items.filter(
      (item): item is ImportPreviewItem & { payload: ExpressionSemanticCreate } =>
        item.payload !== null && item.errors.length === 0
    );
    if (!valid.length) return;
    try {
      setWorking(true);
      const results = await Promise.allSettled(
        valid.map((item) => interactionApi.saveExpression(item.payload))
      );
      const saved = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : []
      );
      const failed = results.length - saved.length;
      const savedMap = new Map(saved.map((item) => [item.id, item]));
      setResources((current) => current.map((item) => savedMap.get(item.id) ?? item));
      setImportPreview(null);
      setNotice(
        zh
          ? `已导入 ${saved.length} 项${failed ? `，${failed} 项失败` : ""}。请逐项审核定义。`
          : `Imported ${saved.length}${failed ? `; ${failed} failed` : ""}. Review each definition.`
      );
      if (failed) {
        const firstFailure = results.find((result) => result.status === "rejected");
        onError(
          firstFailure?.status === "rejected"
            ? String(firstFailure.reason)
            : zh
              ? "部分定义导入失败。"
              : "Some definitions failed to import."
        );
      } else {
        onError("");
      }
    } finally {
      setWorking(false);
    }
  }

  function editor(item: ExpressionSemantic) {
    return (
      <form
        ref={editorRef}
        className="sticker-meaning-editor expression-meaning-editor expression-inline-editor"
        onSubmit={save}
      >
        <div className="sticker-editor-identity">
          <div className="server-sticker-preview compact">
            {item.asset_url ? <img src={item.asset_url} alt="" /> : <span>✦</span>}
          </div>
          <div>
            <strong>{item.name}</strong>
            <small>{profile.guild_name} · {item.resource_key}</small>
          </div>
          <button className="text-button" type="button" onClick={() => setEditing(null)}>
            {zh ? "取消" : "Cancel"}
          </button>
        </div>

        <section className="expression-ai-assistant">
          <NotebookField
            label={zh ? "AI 辅助：描述使用场景" : "AI assist: describe the usage context"}
            guide={
              zh
                ? "例如：轻微吃瓜、期待后续，但不适合严肃道歉。AI 只填入草稿，不会自动保存。"
                : "Example: playful curiosity while waiting for more, but not during a serious apology. AI only fills a draft."
            }
          >
            <NotebookTextarea
              rows={3}
              value={assistantContext}
              onChange={(event) => setAssistantContext(event.currentTarget.value)}
              placeholder={zh ? "这个 Emoji／Sticker 通常什么时候使用？" : "When is this Emoji or Sticker normally used?"}
            />
          </NotebookField>
          <button
            className="paper-button"
            type="button"
            onClick={() => void generateSuggestion(item)}
            disabled={assistantWorking || working}
          >
            {assistantWorking
              ? zh
                ? "生成中…"
                : "Generating…"
              : zh
                ? "AI 生成定义草稿"
                : "Generate definition draft"}
          </button>
          {assistantMessage && <p className="expression-ai-result-note">{assistantMessage}</p>}
        </section>

        <div className="sticker-editor-fields expression-editor-fields">
          <NotebookField label="Intent">
            <NotebookInput name="semantic_intent" defaultValue={item.semantic_intent} />
          </NotebookField>
          <NotebookField label="Emotion">
            <NotebookInput
              name="semantic_emotion"
              defaultValue={item.semantic_emotion}
              placeholder="curious / amused / shy"
            />
          </NotebookField>
          <NotebookField
            className="drawer-form-wide"
            label={zh ? "角色应理解的含义" : "Meaning supplied to characters"}
          >
            <NotebookTextarea
              name="semantic_description"
              rows={5}
              required
              defaultValue={item.semantic_description}
            />
          </NotebookField>
          <NotebookField
            label={zh ? "别名" : "Aliases"}
            guide={zh ? "每行或逗号分隔。" : "One per line or comma."}
          >
            <NotebookTextarea name="aliases" rows={3} defaultValue={item.aliases.join("\n")} />
          </NotebookField>
          <NotebookField
            label={zh ? "适用情境" : "Use when"}
            guide={zh ? "描述适合出现的语境。" : "Describe suitable situations."}
          >
            <NotebookTextarea
              name="situations"
              rows={3}
              defaultValue={item.situations.join("\n")}
            />
          </NotebookField>
          <NotebookField className="drawer-form-wide" label={zh ? "避免情境" : "Avoid when"}>
            <NotebookTextarea
              name="avoid_when"
              rows={3}
              defaultValue={item.avoid_when.join("\n")}
            />
          </NotebookField>
        </div>
        <div className="expression-action-options">
          <label>
            <input type="checkbox" name="enabled" defaultChecked={item.enabled} />
            {zh ? "启用资源" : "Enabled"}
          </label>
          {item.resource_type === "emoji" && (
            <>
              <label>
                <input
                  type="checkbox"
                  name="allow_inline"
                  defaultChecked={item.allowed_actions.includes("inline")}
                />
                Inline
              </label>
              <label>
                <input
                  type="checkbox"
                  name="allow_reaction"
                  defaultChecked={item.allowed_actions.includes("reaction")}
                />
                Reaction
              </label>
            </>
          )}
          {item.resource_type === "sticker" && (
            <label>
              <input
                type="checkbox"
                name="allow_sticker"
                defaultChecked={item.allowed_actions.includes("sticker")}
              />
              Sticker
            </label>
          )}
        </div>
        <button className="ink-button" disabled={working || assistantWorking}>
          {working
            ? zh
              ? "保存中…"
              : "Saving…"
            : zh
              ? "保存 Expression 定义"
              : "Save expression definition"}
        </button>
      </form>
    );
  }

  const visibleResources = resources.filter((item) => item.resource_type === tab);
  const validImportCount = importPreview?.items.filter(
    (item) => item.payload && !item.errors.length
  ).length ?? 0;

  return (
    <section className="server-sticker-section expression-dictionary-section">
      <div className="server-drawer-section-heading">
        <div>
          <p className="tape-label">SERVER EXPRESSIONS</p>
          <h3>{zh ? "Expression Dictionary" : "Expression dictionary"}</h3>
          <p>
            {zh
              ? "Connector 自动同步 Server 自定义 Emoji 与 Sticker。角色模型每轮只看到 Hybrid RAG 检索出的最多 6 个候选。"
              : "The Connector synchronizes custom Emoji and Stickers. The character model sees at most six Hybrid RAG candidates."}
          </p>
        </div>
        <span className="server-sticker-count">{resources.length}</span>
      </div>

      <div className="expression-dictionary-toolbar">
        <p className="expression-dictionary-notice">
          {notice ??
            (zh
              ? "JSON 只更新当前 Server 已同步资源的语义定义，不会更改资源 ID 或图片。"
              : "JSON only updates semantic definitions for resources synchronized in this Server.")}
        </p>
        <div>
          <button className="paper-button" type="button" onClick={exportJson} disabled={!resources.length}>
            {zh ? "导出 JSON + 图片链接" : "Export JSON + image links"}
          </button>
          {!demoMode && (
            <button
              className="paper-button"
              type="button"
              onClick={() => importInputRef.current?.click()}
              disabled={working || loading}
            >
              {zh ? "导入 JSON" : "Import JSON"}
            </button>
          )}
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => void readImportFile(event)}
          />
        </div>
      </div>

      <nav className="expression-dictionary-tabs" aria-label="Expression Dictionary">
        <button type="button" className={tab === "emoji" ? "active" : ""} onClick={() => selectTab("emoji")}>
          Emoji · {resources.filter((item) => item.resource_type === "emoji").length}
        </button>
        <button type="button" className={tab === "sticker" ? "active" : ""} onClick={() => selectTab("sticker")}>
          Sticker · {resources.filter((item) => item.resource_type === "sticker").length}
        </button>
        <button type="button" className={tab === "history" ? "active" : ""} onClick={() => selectTab("history")}>
          {zh ? "决策记录" : "Decision runs"} · {runs.length}
        </button>
      </nav>

      {tab !== "history" && (
        <>
          {loading ? (
            <div className="server-sticker-empty">
              {zh ? "正在同步 Expression Dictionary…" : "Loading Expression Dictionary…"}
            </div>
          ) : visibleResources.length ? (
            <div className="server-sticker-grid">
              {visibleResources.map((item) => {
                const isEditing = editing?.id === item.id;
                return (
                  <Fragment key={item.id}>
                    <article
                      className={`server-sticker-card expression-resource-card${
                        item.available && item.enabled ? "" : " is-muted"
                      }${isEditing ? " is-editing" : ""}`}
                    >
                      <div className="server-sticker-preview">
                        {item.asset_url ? (
                          <img src={item.asset_url} alt="" loading="lazy" />
                        ) : (
                          <span aria-hidden="true">{item.resource_type === "emoji" ? "🙂" : "✦"}</span>
                        )}
                      </div>
                      <div className="server-sticker-copy">
                        <div className="server-sticker-title-row">
                          <strong>{item.name}</strong>
                          <span className={`sticker-source source-${item.semantic_source}`}>
                            {item.semantic_source}
                          </span>
                          {!item.available && <span className="expression-resource-state">unavailable</span>}
                          {!item.enabled && <span className="expression-resource-state">disabled</span>}
                        </div>
                        <small>{item.resource_key} · {item.allowed_actions.join(" / ")}</small>
                        <p>
                          {item.semantic_description ||
                            (zh ? "尚未配置角色语义。" : "No character meaning configured yet.")}
                        </p>
                        <div className="server-sticker-meta">
                          <span>{item.semantic_intent || "—"}</span>
                          <span>{item.semantic_emotion || "—"}</span>
                          <span>{Math.round(item.semantic_confidence * 100)}%</span>
                        </div>
                      </div>
                      {!demoMode && (
                        <button
                          className="paper-button"
                          type="button"
                          aria-expanded={isEditing}
                          onClick={() => toggleEditor(item)}
                        >
                          {isEditing
                            ? zh
                              ? "收起编辑"
                              : "Close editor"
                            : zh
                              ? "编辑定义"
                              : "Edit definition"}
                        </button>
                      )}
                    </article>
                    {isEditing && !demoMode && editor(item)}
                  </Fragment>
                );
              })}
            </div>
          ) : (
            <div className="server-sticker-empty">
              <strong>
                {zh
                  ? `这个 Server 暂时没有可用 ${tab === "emoji" ? "Emoji" : "Sticker"}`
                  : `No available ${tab === "emoji" ? "Emoji" : "Stickers"} in this Server`}
              </strong>
              <p>
                {zh
                  ? "Connector 下次同步 Server Catalog 时会自动获取。"
                  : "The Connector will fetch them during the next Server catalog sync."}
              </p>
            </div>
          )}
        </>
      )}

      {tab === "history" && (
        <section className="expression-run-layout">
          <div className="expression-run-list">
            {runs.length ? (
              runs.map((run) => (
                <button
                  type="button"
                  className={selectedRun?.id === run.id ? "is-active" : ""}
                  key={run.id}
                  onClick={() => void openRun(run)}
                >
                  <span className={`expression-run-status status-${run.status}`}>{run.status}</span>
                  <strong>{run.selected_action}</strong>
                  <small>{run.selected_resource_key || "no resource"}</small>
                  <small>{new Date(run.updated_at).toLocaleString()}</small>
                </button>
              ))
            ) : (
              <div className="server-sticker-empty">
                {zh
                  ? "角色使用 Expression 后会在这里显示节点记录。"
                  : "Expression workflow nodes appear here after a character decision."}
              </div>
            )}
          </div>
          <div className="expression-run-detail">
            {selectedRun ? (
              <>
                <header>
                  <div>
                    <p className="tape-label">EXPRESSION RUN</p>
                    <h4>{selectedRun.id}</h4>
                  </div>
                  <span className={`expression-run-status status-${selectedRun.status}`}>
                    {selectedRun.status}
                  </span>
                </header>
                <dl>
                  <div><dt>{zh ? "当前节点" : "Current node"}</dt><dd>{selectedRun.current_node}</dd></div>
                  <div><dt>{zh ? "尝试次数" : "Attempts"}</dt><dd>{selectedRun.attempt_count}</dd></div>
                  <div><dt>{zh ? "选择动作" : "Selected action"}</dt><dd>{selectedRun.selected_action}</dd></div>
                  <div><dt>{zh ? "资源" : "Resource"}</dt><dd>{selectedRun.selected_resource_key || "—"}</dd></div>
                </dl>
                <div className="expression-node-list">
                  {selectedRun.nodes.map((node) => (
                    <details key={node.id} open={node.status === "failed"}>
                      <summary>
                        <span>{node.node_index}. {node.node_name}</span>
                        <strong>{node.status}</strong>
                      </summary>
                      <small>Attempt {node.attempt}</small>
                      {node.error && <p className="error-note">{node.error}</p>}
                      <div className="expression-node-json">
                        <section>
                          <h5>Input summary</h5>
                          <pre>{JSON.stringify(node.input_summary, null, 2)}</pre>
                        </section>
                        <section>
                          <h5>Output summary</h5>
                          <pre>{JSON.stringify(node.output_summary, null, 2)}</pre>
                        </section>
                      </div>
                    </details>
                  ))}
                </div>
              </>
            ) : (
              <div className="server-sticker-empty">
                {zh ? "选择一条 Run 查看完整节点状态。" : "Select a run to inspect every persisted node."}
              </div>
            )}
          </div>
        </section>
      )}

      {importPreview && (
        <PaperModal
          ariaLabel={zh ? "预览 Expression JSON 导入" : "Preview Expression JSON import"}
          onClose={() => setImportPreview(null)}
          className="expression-import-modal"
        >
          <header>
            <p className="tape-label">JSON IMPORT REVIEW</p>
            <h2>{zh ? "导入前检查匹配结果" : "Review matches before importing"}</h2>
            <p>
              {importPreview.fileName} · {validImportCount} / {importPreview.items.length}{" "}
              {zh ? "项可以导入" : "definitions can be imported"}
            </p>
          </header>
          <div className="expression-import-summary">
            <span>{zh ? `可导入 ${validImportCount}` : `Ready ${validImportCount}`}</span>
            <span>
              {zh
                ? `跳过 ${importPreview.items.length - validImportCount}`
                : `Skipped ${importPreview.items.length - validImportCount}`}
            </span>
          </div>
          <div className="expression-import-list">
            {importPreview.items.map((item, index) => (
              <article
                className={`expression-import-item${item.errors.length ? " is-invalid" : ""}`}
                key={`${item.key}-${index}`}
              >
                {item.resource?.asset_url ? (
                  <img src={item.resource.asset_url} alt="" />
                ) : (
                  <span aria-hidden="true">{item.resource?.resource_type === "sticker" ? "✦" : "🙂"}</span>
                )}
                <div>
                  <strong>{item.resource?.name || item.key}</strong>
                  <small>{item.key}</small>
                  {item.errors.map((error) => <small key={error}>{error}</small>)}
                </div>
                <span className="expression-import-state">
                  {item.errors.length ? (zh ? "跳过" : "Skipped") : zh ? "匹配" : "Matched"}
                </span>
              </article>
            ))}
          </div>
          <footer className="expression-import-actions">
            <button className="paper-button" type="button" onClick={() => setImportPreview(null)}>
              {zh ? "取消" : "Cancel"}
            </button>
            <button
              className="ink-button"
              type="button"
              disabled={!validImportCount || working}
              onClick={() => void confirmImport()}
            >
              {working
                ? zh
                  ? "导入中…"
                  : "Importing…"
                : zh
                  ? `一键导入 ${validImportCount} 项`
                  : `Import ${validImportCount} definitions`}
            </button>
          </footer>
        </PaperModal>
      )}
    </section>
  );
}
