from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Portal API types and methods.
replace_once(
    "web/src/interactionApi.ts",
    '''export interface StickerSemanticCreate {''',
    '''export type ExpressionResourceType = "emoji" | "sticker";
export type ExpressionAction = "none" | "inline" | "reaction" | "sticker";

export interface ExpressionSemantic {
  id: string;
  resource_key: string;
  connection_id: string;
  guild_id: string;
  resource_type: ExpressionResourceType;
  resource_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  animated: boolean;
  available: boolean;
  enabled: boolean;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  aliases: string[];
  situations: string[];
  avoid_when: string[];
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export type ExpressionSemanticCreate = Omit<
  ExpressionSemantic,
  | "id"
  | "resource_key"
  | "semantic_source"
  | "semantic_confidence"
  | "last_seen_at"
  | "created_at"
  | "updated_at"
>;

export interface ExpressionNode {
  id: string;
  node_name: string;
  node_index: number;
  attempt: number;
  status: "running" | "completed" | "failed" | "skipped";
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error: string;
  started_at: string;
  completed_at: string | null;
}

export interface ExpressionRun {
  id: string;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  source_message_id: string;
  deployment_id: string;
  character_card_id: string;
  status: "running" | "completed" | "failed" | "skipped";
  current_node: string;
  attempt_count: number;
  selected_action: ExpressionAction;
  selected_resource_key: string;
  state: Record<string, unknown>;
  last_error: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ExpressionRunDetail extends ExpressionRun {
  nodes: ExpressionNode[];
}

export interface StickerSemanticCreate {''',
)
replace_once(
    "web/src/interactionApi.ts",
    '''  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    })
};''',
    '''  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    }),
  listExpressions: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams();
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<ExpressionSemantic[]>(`/api/discord/expression-dictionary${suffix}`);
  },
  saveExpression: (payload: ExpressionSemanticCreate) =>
    request<ExpressionSemantic>("/api/discord/expression-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  listExpressionRuns: (connectionId?: string, guildId?: string) => {
    const query = new URLSearchParams({ limit: "50" });
    if (connectionId) query.set("connection_id", connectionId);
    if (guildId) query.set("guild_id", guildId);
    return request<ExpressionRun[]>(`/api/discord/expression-runs?${query.toString()}`);
  },
  getExpressionRun: (runId: string) =>
    request<ExpressionRunDetail>(`/api/discord/expression-runs/${runId}`)
};''',
)

# Rename the Server drawer section.
replace_once(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''                  Sticker Dictionary''',
    '''                  Expression Dictionary''',
)

# Event Log recognizes expression workflow events.
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  "runtime_silent",
  "delivery_success",''',
    '''  "runtime_silent",
  "expression_candidates",
  "expression_execution_success",
  "expression_skipped",
  "expression_execution_error",
  "delivery_success",''',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '''  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },
  delivery_success:''',
    '''  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },
  expression_candidates: { en: "Expression candidates retrieved", zh: "已检索表达候选" },
  expression_execution_success: { en: "Expression applied", zh: "表达执行成功" },
  expression_skipped: { en: "Expression skipped", zh: "未使用 Server 表达" },
  expression_execution_error: { en: "Expression failed", zh: "表达执行失败" },
  delivery_success:''',
)

# Expression Dictionary layout, using the existing notebook palette.
css = Path("web/src/discordServerProfiles.css")
current = css.read_text(encoding="utf-8")
addition = r'''

.expression-dictionary-tabs {
  display: flex;
  gap: 7px;
  overflow-x: auto;
  padding: 6px;
  border: 1px dashed rgba(112, 86, 158, 0.22);
  border-radius: 12px;
  background: rgba(255, 253, 247, 0.7);
}

.expression-dictionary-tabs button {
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: rgba(41, 35, 48, 0.66);
  font: inherit;
  font-size: 0.78rem;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
}

.expression-dictionary-tabs button.active {
  border-color: rgba(112, 86, 158, 0.18);
  background: #e9e1fa;
  color: #4f4067;
  transform: rotate(-0.6deg);
}

.expression-resource-card.is-muted {
  opacity: 0.58;
}

.expression-resource-state {
  display: inline-flex;
  padding: 3px 7px;
  border-radius: 999px;
  background: #f4dfe5;
  color: #844f62;
  font-size: 0.66rem;
  font-weight: 800;
}

.expression-editor-fields {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.expression-action-options {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px;
  border: 1px dashed rgba(112, 86, 158, 0.2);
  border-radius: 9px;
}

.expression-action-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
}

.expression-action-options input {
  width: 16px !important;
  min-height: 16px !important;
  margin: 0;
  padding: 0 !important;
}

.expression-run-layout {
  display: grid;
  grid-template-columns: minmax(210px, 0.72fr) minmax(0, 1.45fr);
  gap: 14px;
}

.expression-run-list,
.expression-run-detail,
.expression-node-list {
  display: grid;
  gap: 9px;
  align-content: start;
}

.expression-run-list > button {
  display: grid;
  justify-items: start;
  gap: 4px;
  padding: 12px;
  border: 1px solid rgba(112, 86, 158, 0.14);
  border-radius: 9px;
  background: rgba(255, 253, 247, 0.82);
  color: inherit;
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.expression-run-list > button.is-active {
  border-color: rgba(112, 86, 158, 0.44);
  background: #eee7fa;
}

.expression-run-list small {
  overflow-wrap: anywhere;
  color: rgba(41, 35, 48, 0.58);
}

.expression-run-status {
  display: inline-flex;
  width: fit-content;
  padding: 3px 7px;
  border-radius: 999px;
  background: #e9e1fa;
  font-size: 0.65rem;
  font-weight: 900;
  text-transform: uppercase;
}

.expression-run-status.status-failed { background: #f4dfe5; color: #844f62; }
.expression-run-status.status-completed { background: #dff0e8; color: #35685a; }
.expression-run-status.status-skipped { background: #f7e5d2; color: #80583a; }

.expression-run-detail {
  min-height: 260px;
  padding: 16px;
  border: 1px solid rgba(112, 86, 158, 0.14);
  border-radius: 11px;
  background: rgba(255, 253, 247, 0.82);
}

.expression-run-detail header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.expression-run-detail h4 {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}

.expression-run-detail dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.expression-run-detail dl > div {
  display: grid;
  gap: 3px;
  padding: 9px;
  border-radius: 7px;
  background: rgba(233, 225, 250, 0.45);
}

.expression-run-detail dt {
  color: rgba(41, 35, 48, 0.58);
  font-size: 0.68rem;
  text-transform: uppercase;
}

.expression-run-detail dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 0.78rem;
  font-weight: 700;
}

.expression-node-list details {
  border: 1px solid rgba(112, 86, 158, 0.13);
  border-radius: 8px;
  background: #fffaf2;
}

.expression-node-list summary {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 10px;
  cursor: pointer;
  font-size: 0.76rem;
}

.expression-node-list details > small,
.expression-node-list details > p,
.expression-node-json {
  margin-inline: 10px;
}

.expression-node-json {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding-bottom: 10px;
}

.expression-node-json h5 {
  margin: 0 0 5px;
}

.expression-node-json pre {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 8px;
  border-radius: 6px;
  background: #342b3c;
  color: #fffaf2;
  font-size: 0.66rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .expression-run-layout,
  .expression-editor-fields,
  .expression-node-json {
    grid-template-columns: 1fr;
  }
}
'''
if ".expression-dictionary-tabs" not in current:
    css.write_text(current + addition, encoding="utf-8")
