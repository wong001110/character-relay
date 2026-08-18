export type ParticipationMode =
  | "mention_only"
  | "reply_only"
  | "mention_and_reply"
  | "smart";

export type IdentityMode = "bot" | "webhook";
export type WebhookStatus = "pending" | "active" | "error" | "not_required";
export type ChannelScopeMode = "exact" | "all_except";
export type LangGraphMode = "off" | "condition_watch" | "character_turn" | "social_turn";
export type DeploymentPresenceState = "sleeping" | "idle" | "browsing" | "busy";

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
  presence_state: DeploymentPresenceState;
  presence_activity_type: string;
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
  sticker_id: string | null;
  reaction_emoji: string | null;
  participants: DiscordActionParticipant[];
  plain_text: string;
}

export interface DiscordToolTrace {
  tool_name: string;
  status: "success" | "error";
  result_summary: string;
}

export interface DiscordReply {
  action: "message" | "react" | "sticker" | "silent";
  content: string;
  reason: string;
  deployment_id: string;
  character_display_name: string;
  conversation_id: string;
  turn_index: number;
  smart_output: DiscordSmartOutput | null;
  tool_traces: DiscordToolTrace[];
  media_state?: string;
  media_understanding_attempted?: boolean;
  media_understanding_succeeded?: boolean;
  media_provider?: string;
  media_model?: string;
  media_cache_hit?: boolean;
  media_context_summary?: string;
  provider?: string;
  model?: string;
  orchestration_mode?: LangGraphMode;
  runtime_trace_id?: string;
  generated_media_artifacts?: Array<{
    artifact_id: string;
    filename: string;
    mime_type: string;
    download_url: string;
  }>;
}

export interface DiscordContextMessage {
  message_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  emojis: Array<{
    emoji_id: string;
    name: string;
    animated: boolean;
    asset_url: string;
  }>;
  stickers: Array<{
    sticker_id: string;
    name: string;
    description: string;
    tags: string[];
    format_type: string;
    asset_url: string;
  }>;
  created_at: string;
  is_bot: boolean;
}

export interface DiscordMediaAttachment {
  attachment_id: string;
  filename: string;
  url: string;
  content_type: string;
  size: number;
  width?: number | null;
  height?: number | null;
}

export interface DiscordMediaEmbed {
  embed_type: string;
  url: string;
  title: string;
  description: string;
  image_url: string;
  thumbnail_url: string;
  provider_name: string;
  author_name: string;
}

export interface DiscordMediaReference {
  message_id: string;
  channel_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  attachments: DiscordMediaAttachment[];
  embeds: DiscordMediaEmbed[];
}

export interface DiscordInbound {
  connection_id: string;
  deployment_id: string;
  message_id: string;
  guild_id: string;
  category_id?: string;
  channel_id: string;
  thread_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  context: DiscordContextMessage[];
  attachments: DiscordMediaAttachment[];
  embeds: DiscordMediaEmbed[];
  replied_media_message_id: string;
  replied_media?: DiscordMediaReference | null;
  recent_media?: DiscordMediaReference[];
  source_message_id?: string;
  source_author_id?: string;
  source_author_display_name?: string;
  source_text?: string;
  source_is_bot?: boolean;
  social_role?: string;
  social_depth?: number;
  social_root_message_id?: string;
  social_operation_id?: string;
  participation_reason?: string;
}

export interface DiscordMessageRoute {
  message_id: string;
  deployment_id: string;
  character_card_id: string;
  channel_id: string;
  thread_id: string;
}

export interface DiscordMessageRouteLookup {
  route: DiscordMessageRoute | null;
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

export interface DiscordWebhookRegistrationView {
  binding_id: string;
  webhook_id: string;
  webhook_token: string;
  status: "active";
}

export interface DiscordConnectorHeartbeat {
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

export interface DiscordConnectorEventItem {
  event_id: string;
  occurred_at: string;
  level: "info" | "warning" | "error";
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
  details: Record<string, unknown>;
}

export interface DiscordConnectorEventBatch {
  connection_id: string;
  events: DiscordConnectorEventItem[];
}

export interface DiscordIdentityView {
  deployment_id: string;
  mode: IdentityMode;
  display_name: string;
  avatar_url: string;
  webhook_status: WebhookStatus;
  last_error: string;
  address_aliases: string[];
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

export interface DiscordInteractionRunComplete {
  completed: boolean;
  rounds_completed: number;
  reason: string;
}

export interface DiscordSemanticCandidate {
  deployment_id: string;
  profile_ready: boolean;
  semantic_relevance: number;
  embedding_model: string;
  embedding_dimension: number;
}

export interface DiscordParticipationShadowPlanItem {
  deployment_id: string;
  role: "primary" | "interject" | "complement";
  score: number;
  confidence: number;
  reason: string;
}

export interface DiscordParticipationShadowCandidate {
  deployment_id: string;
  deterministic_score: number;
  semantic_relevance: number;
  final_score: number;
  eligible: boolean;
  selected: boolean;
  reason: string;
  signals: Record<string, number>;
}

export interface DiscordSemanticScore {
  available: boolean;
  reason: string;
  model: string;
  dimension: number;
  candidates: DiscordSemanticCandidate[];
  speaker_plan?: DiscordParticipationShadowPlanItem[];
  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];
  shadow_candidate_scores?: DiscordParticipationShadowCandidate[];
  speaker_plan_authoritative?: boolean;
  conversation_plan_version?: string;
  conversation_planner_used?: boolean;
  conversation_planner_accepted?: boolean;
  conversation_planner_authoritative?: boolean;
  conversation_planner_rollout_bucket?: number;
  conversation_planner_rollout_percent?: number;
  conversation_planner_shadow_plan?: DiscordParticipationShadowPlanItem[];
}

export interface DiscordParticipationCandidatePreflight {
  deployment_id: string;
  eligible: boolean;
  deterministic_score: number;
  minimum_score: number;
  signals: Record<string, number>;
}

export interface DiscordSemanticScoreRequest {
  message: string;
  deployment_ids: string[];
  guild_id: string;
  channel_id: string;
  thread_id: string;
  message_id?: string;
  author_id?: string;
  reply_to_message_id?: string;
  burst_id?: string;
  burst_messages?: Array<{
    message_id: string;
    author_id: string;
    author_display_name: string;
    text: string;
    created_at: string;
    reply_to_message_id: string;
  }>;
  minimum_margin?: number;
  max_participants?: number;
  channel_cooldown_seconds?: number;
  window_seconds?: number;
  max_replies_per_window?: number;
  media_descriptors?: DiscordPlannerMediaDescriptor[];
  media_dependency?: "none" | "optional" | "required";
  media_dependency_locked?: boolean;
  candidate_preflight?: DiscordParticipationCandidatePreflight[];
}

export interface DiscordPlannerMediaDescriptor {
  message_id: string;
  source_ref: string;
  source_kind: "attachment" | "embed" | "url" | "reply" | "recent";
  state: "resolved" | "unsupported" | "private" | "ambiguous" | "error";
  content_kind: "image" | "video" | "article" | "social_post" | "unknown";
  canonical_key: string;
  title: string;
  creator: string;
  duration_seconds: number;
  topic_evidence: string;
  coarse_tags: string[];
  confidence: number;
  opaque_reason: string;
}

export interface DiscordPlannerMediaResult {
  planning_text: string;
  descriptors: DiscordPlannerMediaDescriptor[];
  dependency: "none" | "optional" | "required";
  dependency_locked: boolean;
}

export interface DiscordSmartParticipationOutcomeObservation {
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  message_id: string;
  burst_id: string;
  author_id: string;
  author_display_name: string;
  author_global_name: string;
  author_username: string;
  author_avatar_url: string;
  author_is_bot: boolean;
  reply_to_message_id: string;
  selected_deployment_ids: string[];
  candidate_deployment_ids: string[];
  reason: string;
}

export interface DiscordConversationIntelligenceObservation {
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  message_id: string;
  burst_id: string;
  author_id: string;
  author_display_name: string;
  text: string;
  reply_to_message_id: string;
  selected_deployment_ids: string[];
  candidate_deployment_ids: string[];
  speaker_plan?: DiscordParticipationShadowPlanItem[];
  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];
  shadow_candidate_scores?: DiscordParticipationShadowCandidate[];
  speaker_plan_authoritative?: boolean;
  conversation_plan_version?: string;
  conversation_planner_used?: boolean;
  conversation_planner_accepted?: boolean;
  conversation_planner_authoritative?: boolean;
  conversation_planner_rollout_bucket?: number;
  conversation_planner_rollout_percent?: number;
  conversation_planner_shadow_plan?: DiscordParticipationShadowPlanItem[];
  media_descriptors: DiscordPlannerMediaDescriptor[];
  media_dependency: "none" | "optional" | "required";
  media_dependency_locked: boolean;
  reason: string;
  occurred_at: string;
}

export interface DiscordRecentSpeakerRequest {
  guild_id: string;
  channel_id: string;
  thread_id: string;
  maximum_age_seconds: number;
  allowed_deployment_ids: string[];
}

export interface DiscordRecentSpeakerResponse {
  deployment_id: string;
}

export interface DiscordInteractionClaimRequest {
  guild_id: string;
  channel_id: string;
  target_user_id: string;
  source_message_id: string;
}

export interface DiscordExpressionResolveRequest {
  owner_id: string;
  connection_id: string;
  guild_id: string;
  resource_type: "emoji" | "sticker";
  resource_id: string;
  name: string;
  animated: boolean;
  available: boolean;
  asset_url: string;
  description?: string;
  tags?: string[];
  format_type?: string;
}

export interface DiscordExpressionRetrieveRequest {
  owner_id: string;
  character_card_id: string;
  deployment_id: string;
  connection_id: string;
  guild_id: string;
  query: string;
  interaction_mode: string;
  intensity: string;
  limit: number;
}

export interface DiscordExpressionNodeReport {
  node_type: string;
  status: "pending" | "success" | "failed" | "skipped";
  payload?: Record<string, unknown>;
  error?: string;
}

export interface DiscordDeliveryCursor {
  pending_turns: Array<{
    deployment_id: string;
    role: string;
    depth: number;
    trigger_text: string;
    source_message_id: string;
    source_author_id: string;
    source_author_display_name: string;
    source_is_bot: boolean;
  }>;
  transcript: string[];
  step_index: number;
  continuation_budget_remaining: number;
  participant_deployment_ids: string[];
}

export interface DiscordSocialOperationClaimRequest {
  operation_id: string;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  source_message_id: string;
  initial_deployment_ids: string[];
  available_deployment_ids: string[];
  continuation_budget: number;
  max_depth: number;
}

export interface DiscordSocialOperation {
  operation_id: string;
  owner_id: string;
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  source_message_id: string;
  status: "running" | "completed" | "uncertain" | "failed";
  cursor: DiscordDeliveryCursor;
  max_depth: number;
  initial_deployment_ids: string[];
  available_deployment_ids: string[];
  continuation_budget: number;
  last_error: string;
  pending_step_id: string;
  pending_claim_nonce: string;
  updated_at: string;
}

export interface DiscordDeliveryClaimRequest {
  operation_id: string;
  connection_id: string;
  step_id: string;
  claim_nonce: string;
}

export interface DiscordDeliveryClaimResponse {
  claim_status: "claimed" | "already_claimed" | "already_applied" | "stale";
  operation_status: "running" | "completed" | "uncertain" | "failed";
  operation_id: string;
  step_id: string;
}

export interface DiscordDeliveryAckRequest {
  operation_id: string;
  connection_id: string;
  step_id: string;
  claim_nonce: string;
  cursor: DiscordDeliveryCursor;
  sent_message_ids: string[];
  outgoing_text: string;
  applied: boolean;
  deployment_id: string;
}

export interface DiscordDeliveryFailureRequest {
  operation_id: string;
  connection_id: string;
  step_id: string;
  claim_nonce: string;
  error: string;
}

export interface DiscordSocialTurnStepRequest {
  payload: DiscordInbound;
  selected_deployment_ids: string[];
  available_deployment_ids: string[];
  operation_id?: string;
  cursor?: DiscordDeliveryCursor;
  max_depth?: number;
}

export interface DiscordSocialTurnStepReply {
  reply: DiscordReply;
  cursor: DiscordDeliveryCursor;
  selected_deployment_ids: string[];
  orchestration_mode: LangGraphMode;
  operation_id?: string;
  durable_status?: "fresh" | "replayed";
}

export interface DiscordSocialTurnInterruptRequest {
  connection_id: string;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  operation_id: string;
  superseding_message_id: string;
}

export interface DiscordGeneratedMediaArtifact {
  artifact_id: string;
  filename: string;
  mime_type: string;
  download_url: string;
}
