export type ParticipationMode =
  | "mention_only"
  | "reply_only"
  | "mention_and_reply"
  | "smart";

export type IdentityMode = "bot" | "webhook";
export type WebhookStatus = "pending" | "active" | "error" | "not_required";
export type ChannelScopeMode = "exact" | "all_except";
export type LangGraphMode = "off" | "condition_watch" | "character_turn" | "social_turn";

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
  orchestration_mode: LangGraphMode;
}

export interface DiscordCatalogChannel {
  id: string;
  name: string;
  category_id: string;
  category_name: string;
  type: string;
}

export interface DiscordCatalogEmoji {
  emoji_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  asset_url: string;
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
  emojis: DiscordCatalogEmoji[];
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

export type DiscordExpressionAction = "none" | "inline" | "reaction" | "sticker";

export interface DiscordExpressionContent {
  resource_key: string;
  resource_type: "emoji" | "sticker";
  resource_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  enabled: boolean;
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  asset_url: string;
  format_type: string;
}

export interface DiscordExpressionCandidate extends DiscordExpressionContent {
  score: number;
  signals: Record<string, number>;
}

export interface DiscordExpressionDecision {
  action: DiscordExpressionAction;
  resource_key?: string | null;
  reason: string;
}

export interface DiscordActionParticipant {
  ref: string;
  display_name: string;
  kind: "human" | "character";
}

export type DiscordSmartOutputPart =
  | { text: string }
  | { emoji: string }
  | { mention: string };

export interface DiscordSmartOutput {
  action: "ignore" | "message" | "react" | "sticker";
  content: DiscordSmartOutputPart[];
  reply_to_message_id: string | null;
  target_message_id: string | null;
  emoji_resource_key: string | null;
  sticker_resource_key: string | null;
}

export interface DiscordContextTraceItem {
  knowledge_base_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  score: number;
}

export interface DiscordContextTrace {
  rag_status: "skipped" | "completed" | "failed";
  rag_reason: string;
  retrieval_mode: "current" | "contextual_fallback";
  carryover_message_count: number;
  initial_hit_count: number;
  fallback_hit_count: number;
  query_chars: number;
  eligible_base_count: number;
  candidate_chunk_count: number;
  selected_chunk_count: number;
  selected_knowledge_tokens: number;
  knowledge_token_budget: number;
  selected: DiscordContextTraceItem[];
}

export interface DiscordToolExecutionTrace {
  tool_id: string;
  status: "completed" | "failed" | "rejected";
  duration_ms: number;
  error: string;
}

export interface DiscordExpressionResolveRequest {
  guild_id: string;
  resource_type: "emoji" | "sticker";
  resource_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  asset_url: string;
}

export interface DiscordExpressionRetrieveRequest {
  guild_id: string;
  channel_id: string;
  source_message_id: string;
  deployment_id: string;
  query: string;
  allowed_actions: Array<"inline" | "reaction" | "sticker">;
  excluded_resource_keys: string[];
  top_k: number;
  run_id?: string | null;
}

export interface DiscordExpressionRetrieval {
  run_id: string;
  attempt: number;
  retrieval_backend: "hybrid_sparse_v1";
  candidates: DiscordExpressionCandidate[];
}

export interface DiscordExpressionNodeReport {
  node_name: string;
  status: "running" | "completed" | "failed" | "skipped";
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error: string;
  selected_action?: DiscordExpressionAction | null;
  selected_resource_key?: string | null;
  final_status?: "running" | "completed" | "failed" | "skipped" | null;
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
  emojis: DiscordExpressionContent[];
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
  emojis: DiscordExpressionContent[];
  mentioned_bot: boolean;
  replied_to_bot: boolean;
  reply_to_message_id?: string;
  smart_candidate: boolean;
  author_is_bot: boolean;
  stickers: DiscordStickerContent[];
  burst_media_message_ids?: string[];
  available_characters: string[];
  mentionable_participants: DiscordActionParticipant[];
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
  expression_run_id: string;
  expression_candidates: DiscordExpressionCandidate[];
  runtime_operation_id?: string;
  runtime_step_id?: string;
}

export type DiscordSocialTurnOrigin = "selected" | "invite" | "mention";

export interface DiscordSocialPendingTurn {
  deployment_id: string;
  origin: DiscordSocialTurnOrigin;
  depth: number;
  source_deployment_id: string;
}

export interface DiscordSocialTurnCursor {
  pending_turns: DiscordSocialPendingTurn[];
  completed_deployment_ids: string[];
  continuation_budget_remaining: number;
  max_depth: number;
  step_index: number;
}

export interface DiscordSocialTurnStepRequest {
  payload: DiscordInboundMessage;
  initial_deployment_ids: string[];
  available_deployment_ids: string[];
  continuation_budget: number;
  max_depth: number;
  cursor?: DiscordSocialTurnCursor | null;
  operation_id?: string;
  runtime_step_id?: string;
}

export interface DiscordSocialTurnStepReply {
  reply: DiscordReply;
  cursor: DiscordSocialTurnCursor;
  current_deployment_id: string;
  next_turn?: DiscordSocialPendingTurn | null;
  done: boolean;
  stop_reason: string;
  invite_candidate_deployment_id: string;
  mentioned_character_deployment_ids: string[];
  operation_id?: string;
  step_id?: string;
  step_index?: number;
  durable_status?: "none" | "generated" | "replayed" | "delivered";
  delivery_required?: boolean;
}

export interface DiscordReply {
  action: "silent" | "reply" | "expression";
  reason: string;
  deployment_id?: string | null;
  character_display_name?: string | null;
  text?: string | null;
  reply_to_message_id?: string | null;
  latency_ms?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  expression: DiscordExpressionDecision;
  smart_output?: DiscordSmartOutput | null;
  context_trace?: DiscordContextTrace | null;
  tool_calls: DiscordToolExecutionTrace[];
  generated_artifact_ids: string[];
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
  replica_id: string;
  gateway_ready: boolean;
  state_synchronized: boolean;
  visible_server_count: number;
  event_log_pending_count: number;
  event_log_last_error: string;
  event_log_last_success_at: string;
  event_log_last_recorded_at: string;
  event_log_last_recorded_type: string;
  event_log_sent_count: number;
  last_gateway_message_at: string;
  last_gateway_message_id: string;
  last_gateway_mentioned_bot: boolean;
  turn_collector_enabled: boolean;
  turn_collector_quiet_window_ms: number;
  turn_collector_max_wait_ms: number;
  turn_collector_max_messages: number;
  turn_collector_max_characters: number;
  turn_collector_pending_burst_scope_count: number;
  turn_collector_pending_preflight_scope_count: number;
  turn_collector_candidate_messages: number;
  turn_collector_bypass_messages: number;
  turn_collector_bursts: number;
  turn_collector_collected_messages: number;
  turn_collector_collapsed_messages: number;
  turn_collector_interaction_bypasses: number;
  turn_collector_bypass_reasons: Record<string, number>;
  turn_collector_last_burst_at: string;
  turn_collector_last_burst_id: string;
  turn_collector_last_flush_reason: string;
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
