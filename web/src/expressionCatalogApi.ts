export type ExpressionResourceType = "emoji" | "sticker";
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


import { roomRequest } from "./roomHttp";
export const expressionCatalogApi = {
  list: (connectionId: string, guildId: string) => roomRequest<ExpressionSemantic[]>(`/api/discord/expression-dictionary?${new URLSearchParams({ connection_id: connectionId, guild_id: guildId })}`),
  save: (payload: ExpressionSemanticCreate) => roomRequest<ExpressionSemantic>("/api/discord/expression-dictionary", { method: "PUT", body: JSON.stringify(payload) })
};
