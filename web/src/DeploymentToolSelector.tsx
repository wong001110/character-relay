import { useEffect, useState } from "react";

import { deploymentApi, type ToolCatalogItem } from "./deploymentApi";

interface Props {
  deploymentId?: string | null;
  value: Set<string>;
  onChange: (value: Set<string>) => void;
  disabled?: boolean;
  zh: boolean;
}

export function DeploymentToolSelector({
  deploymentId,
  value,
  onChange,
  disabled = false,
  zh
}: Props) {
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      deploymentApi.listToolCatalog(),
      deploymentId ? deploymentApi.getDeploymentTools(deploymentId) : Promise.resolve(null)
    ])
      .then(([nextCatalog, profile]) => {
        if (!active) return;
        setCatalog(nextCatalog.items);
        if (profile) onChange(new Set(profile.enabled_tools));
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

  function toggle(toolId: string) {
    const next = new Set(value);
    if (next.has(toolId)) next.delete(toolId);
    else next.add(toolId);
    onChange(next);
  }

  return (
    <section className="deployment-form-wide deployment-tool-selector">
      <div className="deployment-form-divider">
        <strong>{zh ? "角色工具 / Tool Calling" : "Character tools / Tool Calling"}</strong>
        <span>
          {zh
            ? "只把勾选的工具提供给这个 Deployment 的角色。不同 Deployment 可以分配不同能力；目前不使用 embedding 做 Tool Retrieval。"
            : "Only checked tools are exposed to this Deployment. The same Character Card may receive different capabilities elsewhere; Tool Retrieval does not use embeddings yet."}
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
          {catalog.map((tool) => (
            <label className="deployment-tool-option" key={tool.id}>
              <input
                type="checkbox"
                checked={value.has(tool.id)}
                disabled={disabled}
                onChange={() => toggle(tool.id)}
              />
              <span>
                <strong>{tool.display_name}</strong>
                <small>{tool.id}</small>
                <small>{tool.description}</small>
              </span>
              <em>{tool.operation} · {tool.risk}</em>
            </label>
          ))}
        </div>
      )}
    </section>
  );
}
