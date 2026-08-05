export type ParticipationMode =
  | "mention_only"
  | "reply_only"
  | "mention_and_reply"
  | "smart";

export type IdentityMode = "bot" | "webhook";
export type WebhookStatus = "pending" | "active" | "error" | "not_required";
export type ChannelScopeMode = "exact" | "all_except";

export interface DiscordDeployment {
  deployment_id: string;
  connection_id: string;
  character_card_id: string;
  character_display_name: string;
  workspace_id: string;
  workspace_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  category_id: string;
  server_profile_id: string;
  channel_scope_mode: ChannelScopeMode;
  excluded_channel_ids: string[];
  excluded_category_ids: string[];
  participation_mode: ParticipationMode;
  version_label: string;
  status: "active";
  identity_mode: IdentityMode;
  identity_display_name: string;
  identity_avatar_url: string;
  address_aliases?: string[];
  webhook_status: WebhookStatus;
  webhook_id?: string | null;
  webhook_token?: string | null;
}

export interface DiscordCatalogChannel {
  id: string;
  name: string;
  category_id: string;
  category_name: string;
  type: string;
}

export interface DiscordCatalogSticker {
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
}

export interface DiscordCatalogServer {
  guild_id: string;
  guild_name: string;
  channels: DiscordCatalogChannel[];
  stickers: DiscordCatalogSticker[];
}

export interface DiscordServerCatalogSync {
  connection_id: string;
  servers: DiscordCatalogServer[];
}

export interface DiscordStickerContent {
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
}

export interface DiscordStickerObservation {
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
}

export interface DiscordInteractionSession {
  id: string;
  participant_deployment_ids: string[];
  rounds_per_trigger: number;
  intensity: "light" | "playful" | "sharp";
  target_user_id: string;
  target_display_name: string;
}

export interface DiscordInteractionClaim {
  claimed: boolean;
  run_id: string | null;
  session: DiscordInteractionSession | null;
}

export interface DiscordInteractionClaimRequest {
  guild_id: string;
  channel_id: string;
  target_user_id: string;
  source_message_id: string;
}

export interface DiscordInteractionRunComplete {
  status: "completed" | "failed";
  reply_count: number;
  stop_reason: string;
}

export interface DiscordContextMessage {
  message_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  stickers: DiscordStickerContent[];
  created_at?: string;
  is_bot: boolean;
}

export interface DiscordInboundMessage {
  connection_id: string;
  deployment_id: string;
  message_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  thread_id: string;
  thread_name: string;
  author_id: string;
  author_display_name: string;
  text: string;
  mentioned_bot: boolean;
  replied_to_bot: boolean;
  smart_candidate: boolean;
  author_is_bot: boolean;
  stickers: DiscordStickerContent[];
  available_characters: string[];
  recent_messages: DiscordContextMessage[];
  interaction_session_id: string;
  interaction_type: string;
  interaction_intensity: string;
  interaction_round: number;
  interaction_total_rounds: number;
  interaction_position: number;
  interaction_participant_count: number;
  interaction_target_user_id: string;
  interaction_target_display_name: string;
}

export interface DiscordReply {
  action: "silent" | "reply";
  reason: string;
  deployment_id?: string | null;
  character_display_name?: string | null;
  text?: string | null;
  reply_to_message_id?: string | null;
  latency_ms?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
}

export type DiscordConnectorEventLevel = "info" | "warning" | "error";

export interface DiscordConnectorEvent {
  id: string;
  occurred_at: string;
  level: DiscordConnectorEventLevel;
  event_type: string;
  message: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  thread_id: string;
  thread_name: string;
  source_message_id: string;
  deployment_id: string;
  character_name: string;
  details: Record<string, unknown>;
}

export interface DiscordConnectorEventBatch {
  connection_id: string;
  events: DiscordConnectorEvent[];
}

export interface ConnectorHeartbeat {
  connection_id: string;
  bot_user_id: string;
  bot_display_name: string;
  status: "connected" | "offline" | "error";
  last_error: string;
  replica_region: string;
  gateway_ready: boolean;
  state_synchronized: boolean;
  visible_server_count: number;
}

export interface DiscordWebhookRegistration {
  connection_id: string;
  deployment_id: string;
  workspace_id: string;
  channel_id: string;
  category_id: string;
  thread_id: string;
  webhook_id: string;
  webhook_token: string;
}

export interface DiscordWebhookRegistrationResult {
  binding_id: string;
  webhook_id: string;
  webhook_token: string;
  status: "active";
}

export interface DiscordWebhookStatusReport {
  deployment_id: string;
  status: WebhookStatus;
  last_error: string;
}

export interface DiscordMessageRouteRegistration {
  connection_id: string;
  deployment_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  webhook_id: string;
  message_ids: string[];
}

export interface DiscordMessageRouteView {
  message_id: string;
  deployment_id: string;
  character_card_id: string;
  channel_id: string;
  thread_id: string;
}

export interface DiscordMessageRouteLookup {
  route: DiscordMessageRouteView | null;
}
