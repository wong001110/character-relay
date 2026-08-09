import { useEffect, useMemo, useState } from "react";

import { deploymentApi, type ToolCatalogItem } from "./deploymentApi";
import { useI18n } from "./i18n";
import {
  toolTestApi,
  type ToolTestDeployment,
  type ToolTestResult
} from "./toolTestApi";

function starterArguments(toolId: string): string {
  const values: Record<string, Record<string, unknown>> = {
    "utility.calculator": { expression: "2 + 2" },
    "utility.current_time": {},
    "web.search": { query: "Character Relay", count: 3 },
    "web.fetch_page": { url: "https://example.com", max_chars: 1200 },
    "discord.search_messages": { query: "test", limit: 5 },
    "discord.create_poll": {
      question: "Tool Calling test poll",
      answers: ["A", "B"],
      duration_hours: 1,
      allow_multiselect: false
    },
    "weather.get": { location: "Kuala Lumpur", days: 1 },
    "random.roll": { dice: "1d20" },
    "random.choose": { options: ["A", "B"] },
    "image.search": { query: "Kuala Lumpur skyline", count: 3 },
    "scheduler.remind": {
      reminder_text: "Character Relay Tool Calling test reminder",
      delay_seconds: 60,
      mention_user: false
    },
    "scheduler.list": { limit: 20, include_finished: false },
    "scheduler.cancel": { reminder_id: "" },
    "watch.condition": {
      condition_text: "Character Relay V2 is publicly released",
      notification_text: "Character Relay V2 is publicly released now.",
      check_interval_seconds: 300,
      expires_in_seconds: 3600,
      max_attempts: 12,
      mention_user: false
    },
    "places.search": { query: "coffee", location: "Kuala Lumpur", count: 3 },
    "file.inspect": {}
  };
  return JSON.stringify(values[toolId] ?? {}, null, 2);
}

function deploymentLabel(item: ToolTestDeployment): string {
  const destination = item.thread_name || item.channel_name || item.guild_id || item.platform;
  return `${item.character_name} · ${destination} · ${item.deployment_id.slice(0, 8)}`;
}

export function ToolCallingTestPanel({ onClose }: { onClose: () => void }) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [deployments, setDeployments] = useState<ToolTestDeployment[]>([]);
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [toolId, setToolId] = useState("");
  const [argumentsText, setArgumentsText] = useState("{}");
  const [guildId, setGuildId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [threadId, setThreadId] = useState("");
  const [messageId, setMessageId] = useState("");
  const [initiatorUserId, setInitiatorUserId] = useState("");
  const [triggerText, setTriggerText] = useState("Super Admin Tool Calling test");
  const [confirmSideEffect, setConfirmSideEffect] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ToolTestResult | null>(null);

  const selectedDeployment = useMemo(
    () => deployments.find((item) => item.deployment_id === deploymentId) ?? null,
    [deployments, deploymentId]
  );
  const enabledTools = useMemo(
    () =>
      catalog.filter((item) => selectedDeployment?.enabled_tools.includes(item.id) ?? false),
    [catalog, selectedDeployment]
  );
  const selectedTool = useMemo(
    () => enabledTools.find((item) => item.id === toolId) ?? null,
    [enabledTools, toolId]
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([toolTestApi.listDeployments(), deploymentApi.listToolCatalog()])
      .then(([nextDeployments, nextCatalog]) => {
        if (!active) return;
        setDeployments(nextDeployments);
        setCatalog(nextCatalog.items);
        const first = nextDeployments.find((item) => item.enabled_tools.length > 0) ?? nextDeployments[0];
        if (first) setDeploymentId(first.deployment_id);
        setError(null);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedDeployment) return;
    setGuildId(selectedDeployment.guild_id);
    setChannelId(selectedDeployment.channel_id);
    setThreadId(selectedDeployment.thread_id);
    const firstTool = catalog.find((item) => selectedDeployment.enabled_tools.includes(item.id));
    setToolId(firstTool?.id ?? "");
    setArgumentsText(starterArguments(firstTool?.id ?? ""));
    setConfirmSideEffect(false);
    setResult(null);
  }, [selectedDeployment?.deployment_id, catalog]);

  function changeTool(nextToolId: string) {
    setToolId(nextToolId);
    setArgumentsText(starterArguments(nextToolId));
    setConfirmSideEffect(false);
    setResult(null);
    setError(null);
  }

  async function execute() {
    if (!selectedDeployment || !selectedTool) return;
    let args: Record<string, unknown>;
    try {
      const parsed = JSON.parse(argumentsText) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error(zh ? "Arguments 必须是 JSON object。" : "Arguments must be a JSON object.");
      }
      args = parsed as Record<string, unknown>;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return;
    }

    try {
      setRunning(true);
      setError(null);
      setResult(null);
      const next = await toolTestApi.execute({
        deployment_id: selectedDeployment.deployment_id,
        tool_id: selectedTool.id,
        arguments: args,
        guild_id: guildId.trim(),
        channel_id: channelId.trim(),
        thread_id: threadId.trim(),
        message_id: messageId.trim(),
        initiator_user_id: initiatorUserId.trim(),
        trigger_text: triggerText.trim(),
        confirm_side_effect: confirmSideEffect
      });
      setResult(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="tool-test-panel">
      <header className="tool-test-header">
        <div>
          <p className="tape-label">SUPER ADMIN / TOOL CALLING</p>
          <h2>{zh ? "Tool Calling 手动测试" : "Tool Calling manual test"}</h2>
          <p>
            {zh
              ? "直接调用 Deployment 已启用的真实 Runtime Tool，不经过 LLM。这里用来区分 Tool 本身是否正常，以及模型有没有决定调用它。"
              : "Execute a real Runtime Tool enabled on a Deployment without involving the LLM. This isolates Tool health from the model's decision to call it."}
          </p>
        </div>
        <button type="button" className="paper-button" onClick={onClose}>
          {zh ? "返回" : "Back"}
        </button>
      </header>

      {error && <p className="error-note">{error}</p>}

      {loading ? (
        <div className="tool-test-empty">{zh ? "正在读取 Deployment 与 Tool…" : "Loading Deployments and Tools…"}</div>
      ) : (
        <div className="tool-test-layout">
          <div className="tool-test-form">
            <label>
              {zh ? "Deployment" : "Deployment"}
              <select value={deploymentId} onChange={(event) => setDeploymentId(event.currentTarget.value)}>
                {deployments.map((item) => (
                  <option key={item.deployment_id} value={item.deployment_id}>
                    {deploymentLabel(item)}
                  </option>
                ))}
              </select>
            </label>

            {selectedDeployment && (
              <div className="tool-test-runtime-note">
                <strong>{selectedDeployment.character_name}</strong>
                <span>{selectedDeployment.platform} · {selectedDeployment.timezone}</span>
                <code>{selectedDeployment.owner_id.slice(0, 12)} / {selectedDeployment.deployment_id}</code>
              </div>
            )}

            <label>
              Tool
              <select value={toolId} onChange={(event) => changeTool(event.currentTarget.value)}>
                {enabledTools.length === 0 && <option value="">No enabled Tools</option>}
                {enabledTools.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name} · {item.id}
                  </option>
                ))}
              </select>
            </label>

            {selectedTool && (
              <div className="tool-test-tool-note">
                <div>
                  <strong>{selectedTool.display_name}</strong>
                  <span>{selectedTool.category} · {selectedTool.operation} · {selectedTool.risk} risk</span>
                </div>
                <span className={selectedTool.side_effect ? "tool-test-side-effect" : "tool-test-read-only"}>
                  {selectedTool.side_effect ? "SIDE EFFECT" : "READ ONLY"}
                </span>
                <p>{selectedTool.description}</p>
              </div>
            )}

            <label className="tool-test-wide">
              Arguments JSON
              <textarea
                rows={12}
                spellCheck={false}
                value={argumentsText}
                onChange={(event) => setArgumentsText(event.currentTarget.value)}
              />
            </label>

            <div className="tool-test-context-grid tool-test-wide">
              <label>
                Guild ID
                <input value={guildId} onChange={(event) => setGuildId(event.currentTarget.value)} />
              </label>
              <label>
                Channel ID
                <input
                  value={channelId}
                  onChange={(event) => setChannelId(event.currentTarget.value)}
                  placeholder={zh ? "Server-wide Deployment 的 Discord/Watch Tool 需要填写" : "Required for Discord/Watch Tools on server-wide deployments"}
                />
              </label>
              <label>
                Thread ID
                <input value={threadId} onChange={(event) => setThreadId(event.currentTarget.value)} />
              </label>
              <label>
                Initiator User ID
                <input
                  value={initiatorUserId}
                  onChange={(event) => setInitiatorUserId(event.currentTarget.value)}
                />
              </label>
              <label>
                Message ID
                <input value={messageId} onChange={(event) => setMessageId(event.currentTarget.value)} />
              </label>
              <label>
                Trigger text
                <input value={triggerText} onChange={(event) => setTriggerText(event.currentTarget.value)} />
              </label>
            </div>

            {selectedTool?.side_effect && (
              <label className="tool-test-confirm tool-test-wide">
                <input
                  type="checkbox"
                  checked={confirmSideEffect}
                  onChange={(event) => setConfirmSideEffect(event.currentTarget.checked)}
                />
                <span>
                  {zh
                    ? "我确认这会执行真实 side effect（例如建立 Reminder、Condition Watch 或 Discord Poll）。"
                    : "I confirm this executes the real side effect (for example creating a Reminder, Condition Watch, or Discord Poll)."}
                </span>
              </label>
            )}

            <div className="tool-test-actions tool-test-wide">
              <button
                type="button"
                className="ink-button"
                disabled={
                  running ||
                  !selectedDeployment ||
                  !selectedTool ||
                  (selectedTool.side_effect && !confirmSideEffect)
                }
                onClick={() => void execute()}
              >
                {running ? (zh ? "执行中…" : "Executing…") : zh ? "执行 Runtime Tool" : "Execute Runtime Tool"}
              </button>
            </div>
          </div>

          <aside className="tool-test-result">
            <p className="tape-label">TOOL RESULT</p>
            {!result ? (
              <div className="tool-test-empty">
                {zh ? "执行后会显示 completed / rejected / failed 与原始 Tool Result。" : "Run a Tool to inspect completed / rejected / failed status and the raw Tool Result."}
              </div>
            ) : (
              <>
                <div className="tool-test-result-heading">
                  <span className={`tool-test-status tool-test-${result.status}`}>{result.status}</span>
                  <strong>{result.provider_function_name}</strong>
                </div>
                <dl className="tool-test-meta">
                  <div><dt>Tool</dt><dd>{result.tool_id}</dd></div>
                  <div><dt>Duration</dt><dd>{result.duration_ms} ms</dd></div>
                  <div><dt>Timezone</dt><dd>{result.timezone}</dd></div>
                  <div><dt>Side effect</dt><dd>{result.side_effect ? "yes" : "no"}</dd></div>
                </dl>
                {result.error && <p className="error-note">{result.error}</p>}
                <pre>{JSON.stringify(result.result, null, 2)}</pre>
              </>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
