export type ParticipationMode =
  | "mention_only"
  | "reply_only"
  | "mention_and_reply"
  | "smart";

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
  participation_mode: ParticipationMode;
  version_label: string;
  status: "active";
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
  message_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
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
