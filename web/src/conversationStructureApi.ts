export interface ConversationThreadObservation {
  id: string;
  canonical_label: string;
  anchor_summary: string;
  working_summary: string;
  representative_segment_ids: string[];
  participant_ids: string[];
  active_entity_ids: string[];
  status: string;
  last_active_at: string;
}

export interface ConversationSegmentObservation {
  id: string;
  burst_id: string;
  message_ids: string[];
  participant_ids: string[];
  kind: string;
  summary: string;
  thread_id: string;
  membership_relation: string;
  membership_confidence: number;
  confidence: number;
  source: string;
  created_at: string;
}

export interface MessageRelationObservation {
  id: string;
  source_message_id: string;
  relation_class: string;
  relation_type: string;
  target_ref_type: string;
  target_ref: string;
  confidence: number;
  source: string;
  evidence_refs: string[];
  status: string;
  supersedes_relation_id: string;
  created_at: string;
}

export interface EpisodeObservation {
  id: string;
  conversation_thread_id: string;
  segment_ids: string[];
  source_message_ids: string[];
  participant_ids: string[];
  entity_ids: string[];
  media_refs: string[];
  summary: string;
  key_events: string[];
  status: string;
  checkpoint_reason: string;
  ended_at: string;
}

export interface EntityObservation {
  id: string;
  entity_type: string;
  canonical_name: string;
  aliases: string[];
  status: string;
  merged_into_entity_id: string;
  metadata: Record<string, string>;
  source_refs: string[];
}

export interface KnowledgeGapObservation {
  id: string;
  entity_id: string;
  missing_fields: string[];
  importance: number;
  resolution_state: string;
  discovery_requested: boolean;
  possible_sources: string[];
  resolution_evidence_refs: string[];
}

export interface BeliefObservation {
  id: string;
  character_card_id: string;
  subject_entity_id: string;
  subject_ref: string;
  predicate: string;
  value_text: string;
  authority_class: string;
  authority_score: number;
  confidence: number;
  status: string;
  authored: boolean;
  evidence_refs: string[];
  dependency_edge_ids: string[];
  supersedes_belief_id: string;
  updated_at: string;
}

export interface SocialEventObservation {
  id: string;
  source_deployment_id: string;
  target_type: string;
  target_key: string;
  event_type: string;
  confidence: number;
  status: string;
  source_relation_id: string;
  source_segment_id: string;
  source_episode_id: string;
  reason: string;
  created_at: string;
}

export interface ImpressionObservation {
  id: string;
  source_deployment_id: string;
  target_type: string;
  target_key: string;
  summary: string;
  observations: string[];
  evidence_refs: string[];
  confidence: number;
  status: string;
  supersedes_impression_id: string;
  updated_at: string;
}

export interface ConversationStructureView {
  deployment_id: string;
  threads: ConversationThreadObservation[];
  segments: ConversationSegmentObservation[];
  relations: MessageRelationObservation[];
  episodes: EpisodeObservation[];
  entities: EntityObservation[];
  knowledge_gaps: KnowledgeGapObservation[];
  beliefs: BeliefObservation[];
  social_events: SocialEventObservation[];
  impressions: ImpressionObservation[];
}

export async function loadConversationStructure(
  deploymentId: string
): Promise<ConversationStructureView> {
  const response = await fetch(
    `/api/deployments/${encodeURIComponent(deploymentId)}/conversation-structure`,
    { credentials: "include" }
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<ConversationStructureView>;
}
