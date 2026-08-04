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

export interface DiscordCatalogServer {
  guild_id: string;
  guild_name: string;
  channels: DiscordCatalogChannel[];
}

export interface DiscordServerCatalogSync {
  connection_id: string;
  servers: DiscordCatalogServer[];
}

export interface DiscordContextMessage {
  message_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
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
  recent_messages: DiscordContextMessage[];
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

export interface ConnectorHeartbeat {
  connection_id: string;
  bot_user_id: string;
  bot_display_name: string;
  status: "connected" | "offline" | "error";
  last_error: string;
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
