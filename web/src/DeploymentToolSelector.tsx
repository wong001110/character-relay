import { useEffect, useState } from "react";

import { deploymentApi, type ToolCatalogItem } from "./deploymentApi";

interface Props {
  deploymentId: string;
  disabled?: boolean;
  zh: boolean;
}

type ToolCatalogItemWithAvailability = ToolCatalogItem & {
  available?: boolean;
  availability_reason?: string;
};

export function DeploymentToolSelector({
  deploymentId,
  disabled = false,
  zh
}: Props) {
  const [catalog, setCatalog] = useState<ToolCatalogItemWithAvailability[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      deploymentApi.listToolCatalog(),
      deploymentApi.getDeploymentTools(deploymentId)
    ])
      .then(([nextCatalog, profile]) => {
        if (!active) return;
        setCatalog(nextCatalog.items);
        setEnabled(new Set(profile.enabled_tools));
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deploymentId]);

  async function toggle(toolId: string) {
    if (saving || disabled) return;
    const previous = enabled;
    const next = new Set(enabled);
    if (next.has(toolId)) next.delete(toolId);
    else next.add(toolId);
    setEnabled(next);
    try {
      setSaving(true);
      setError("");
      const saved = await deploymentApi.updateDeploymentTools(deploymentId, [...next]);
      setEnabled(new Set(saved.enabled_tools));
    } catch (reason) {
      setEnabled(previous);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="deployment-form-wide deployment-tool-selector">
      <div className="deployment-form-divider">
        <strong>{zh ? "角色工具 / Tool Calling" : "Character tools / Tool Calling"}</strong>
        <span>
          {zh
            ? "只把勾选的工具提供给这个 Deployment 的角色。不同 Deployment 可以分配不同能力；目前不使用 embedding 做 Tool Retrieval。勾选后会立即保存。"
            : "Only checked tools are exposed to this Deployment. The same Character Card may receive different capabilities elsewhere; Tool Retrieval does not use embeddings yet. Changes save immediately."}
        </span>
      </div>
      {loading ? (
        <small>{zh ? "读取可用工具…" : "Loading available tools…"}</small>
      ) : error ? (
        <small className="deployment-inline-error">{error}</small>
      ) : catalog.length === 0 ? (
        <small>{zh ? "目前没有可分配工具。" : "No assignable tools are available."}</small>
      ) : (
        <div className="deployment-tool-grid">
          {catalog.map((tool) => {
            const unavailable = tool.available === false;
            const isEnabled = enabled.has(tool.id);
            return (
              <label
                className={`deployment-tool-option${unavailable ? " is-unavailable" : ""}`}
                key={tool.id}
              >
                <input
                  type="checkbox"
                  checked={isEnabled}
                  disabled={disabled || saving || (unavailable && !isEnabled)}
                  onChange={() => void toggle(tool.id)}
                />
                <span>
                  <strong>{tool.display_name}</strong>
                  <small>{tool.id}</small>
                  <small>{tool.description}</small>
                  {unavailable && tool.availability_reason && (
                    <small className="deployment-inline-error">
                      {zh ? "尚未配置：" : "Unavailable: "}
                      {tool.availability_reason}
                    </small>
                  )}
                </span>
                <em>
                  {tool.operation} · {tool.risk}
                  {unavailable ? ` · ${zh ? "不可用" : "unavailable"}` : ""}
                </em>
              </label>
            );
          })}
        </div>
      )}
    </section>
  );
}
