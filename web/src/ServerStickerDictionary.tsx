import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type FormEvent
} from "react";

import type { DiscordServerProfile } from "./deploymentApi";
import {
  interactionApi,
  type ExpressionRun,
  type ExpressionRunDetail,
  type ExpressionSemantic
} from "./interactionApi";
import {
  NotebookField,
  NotebookInput,
  NotebookTextarea
} from "./NotebookUI";

interface Props {
  profile: DiscordServerProfile;
  demoMode: boolean;
  zh: boolean;
  onError: (message: string) => void;
}

type DictionaryTab = "emoji" | "sticker" | "history";

function splitLines(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(/[,，\n]/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ServerStickerDictionary({ profile, demoMode, zh, onError }: Props) {
  const [resources, setResources] = useState<ExpressionSemantic[]>([]);
  const [runs, setRuns] = useState<ExpressionRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ExpressionRunDetail | null>(null);
  const [editing, setEditing] = useState<ExpressionSemantic | null>(null);
  const [tab, setTab] = useState<DictionaryTab>("emoji");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const editorRef = useRef<HTMLFormElement | null>(null);

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
    void load();
  }, [profile.connection_id, profile.guild_id]);

  useEffect(() => {
    if (!editing) return;
    const timer = window.setTimeout(() => {
      editorRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [editing?.id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const allowedActions = ["inline", "reaction", "sticker"].filter(
      (action) => data.get(`allow_${action}`) === "on"
    ) as Array<"inline" | "reaction" | "sticker">;
    try {
      setWorking(true);
      const saved = await interactionApi.saveExpression({
        connection_id: editing.connection_id,
        guild_id: editing.guild_id,
        resource_type: editing.resource_type,
        resource_id: editing.resource_id,
        name: editing.name,
        description: editing.description,
        tags: editing.tags,
        format_type: editing.format_type,
        asset_url: editing.asset_url,
        animated: editing.animated,
        available: editing.available,
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
      });
      setResources((current) =>
        current.map((item) => (item.id === saved.id ? saved : item))
      );
      setEditing(null);
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
    setTab(nextTab);
  }

  function toggleEditor(item: ExpressionSemantic) {
    setEditing((current) => (current?.id === item.id ? null : item));
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
        <button className="ink-button" disabled={working}>
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

  return (
    <section className="server-sticker-section expression-dictionary-section">
      <div className="server-drawer-section-heading">
        <div>
          <p className="tape-label">SERVER EXPRESSIONS</p>
          <h3>{zh ? "Expression Dictionary" : "Expression dictionary"}</h3>
          <p>
            {zh
              ? "Connector 自动同步 Server 自定义 Emoji 与 Sticker。角色模型每轮只看到 Hybrid RAG 检索出的最多 6 个候选，不会把整套资源塞进 Prompt。"
              : "The Connector synchronizes custom Emoji and Stickers. The character model sees at most six Hybrid RAG candidates instead of the entire Server dictionary."}
          </p>
        </div>
        <span className="server-sticker-count">{resources.length}</span>
      </div>

      <nav className="expression-dictionary-tabs" aria-label="Expression Dictionary">
        <button
          type="button"
          className={tab === "emoji" ? "active" : ""}
          onClick={() => selectTab("emoji")}
        >
          Emoji · {resources.filter((item) => item.resource_type === "emoji").length}
        </button>
        <button
          type="button"
          className={tab === "sticker" ? "active" : ""}
          onClick={() => selectTab("sticker")}
        >
          Sticker · {resources.filter((item) => item.resource_type === "sticker").length}
        </button>
        <button
          type="button"
          className={tab === "history" ? "active" : ""}
          onClick={() => selectTab("history")}
        >
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
                          <span aria-hidden="true">
                            {item.resource_type === "emoji" ? "🙂" : "✦"}
                          </span>
                        )}
                      </div>
                      <div className="server-sticker-copy">
                        <div className="server-sticker-title-row">
                          <strong>{item.name}</strong>
                          <span className={`sticker-source source-${item.semantic_source}`}>
                            {item.semantic_source}
                          </span>
                          {!item.available && (
                            <span className="expression-resource-state">unavailable</span>
                          )}
                          {!item.enabled && (
                            <span className="expression-resource-state">disabled</span>
                          )}
                        </div>
                        <small>{item.resource_key} · {item.allowed_actions.join(" / ")}</small>
                        <p>
                          {item.semantic_description ||
                            (zh
                              ? "尚未配置角色语义。"
                              : "No character meaning configured yet.")}
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
                  <span className={`expression-run-status status-${run.status}`}>
                    {run.status}
                  </span>
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
                  <div>
                    <dt>{zh ? "当前节点" : "Current node"}</dt>
                    <dd>{selectedRun.current_node}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "尝试次数" : "Attempts"}</dt>
                    <dd>{selectedRun.attempt_count}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "选择动作" : "Selected action"}</dt>
                    <dd>{selectedRun.selected_action}</dd>
                  </div>
                  <div>
                    <dt>{zh ? "资源" : "Resource"}</dt>
                    <dd>{selectedRun.selected_resource_key || "—"}</dd>
                  </div>
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
                {zh
                  ? "选择一条 Run 查看完整节点状态。"
                  : "Select a run to inspect every persisted node."}
              </div>
            )}
          </div>
        </section>
      )}
    </section>
  );
}
