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
  source_author_id: string;
  source_author_display_name: string;
  relation_class: string;
  relation_type: string;
  target_ref_type: string;
  target_ref: string;
  target_author_id: string;
  target_author_display_name: string;
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

export interface KnowledgeGapCandidate {
  id: string;
  gap_id: string;
  discovery_item_id: string;
  source: string;
  canonical_key: string;
  content_kind: string;
  title: string;
  creator: string;
  url: string;
  score: number;
  rank_reason: string;
  status: "ready" | "accepted" | "rejected" | "expired";
  validation_method: string;
  validated_evidence_ref: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  expires_at: string;
}

export interface BeliefDetail extends BeliefObservation {
  scope: string;
  origin: string;
  importance: number;
  valid_from: string | null;
  valid_to: string | null;
  stale_after: string | null;
}

export interface BeliefManagementResult {
  action: string;
  belief: BeliefDetail;
  previous_belief_ids: string[];
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

export type ConversationCollection =
  | "threads"
  | "segments"
  | "relations"
  | "episodes"
  | "entities"
  | "knowledge_gaps"
  | "beliefs"
  | "social_events"
  | "impressions";

export interface ConversationPage<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
  /** False when the response came from the legacy bounded-array contract. */
  paged: boolean;
}

export type ConversationStructurePages = {
  [K in ConversationCollection]: ConversationPage<
    K extends "threads" ? ConversationThreadObservation :
    K extends "segments" ? ConversationSegmentObservation :
    K extends "relations" ? MessageRelationObservation :
    K extends "episodes" ? EpisodeObservation :
    K extends "entities" ? EntityObservation :
    K extends "knowledge_gaps" ? KnowledgeGapObservation :
    K extends "beliefs" ? BeliefObservation :
    K extends "social_events" ? SocialEventObservation :
    ImpressionObservation
  >;
};

export interface ConversationStructurePage extends ConversationStructureView {
  pages: ConversationStructurePages;
}

type CollectionPayload<T> =
  | T[]
  | { items?: T[]; next_cursor?: string | null; has_more?: boolean };

function collectionPage<T>(
  raw: CollectionPayload<T> | undefined,
  metadata: { next_cursor?: string | null; has_more?: boolean } | undefined
): ConversationPage<T> {
  if (Array.isArray(raw)) {
    const paged = metadata?.next_cursor !== undefined || metadata?.has_more !== undefined;
    return {
      items: raw,
      next_cursor: metadata?.next_cursor ?? null,
      has_more: metadata?.has_more ?? metadata?.next_cursor != null,
      paged
    };
  }
  return {
    items: raw?.items ?? [],
    next_cursor: raw?.next_cursor ?? metadata?.next_cursor ?? null,
    has_more: raw?.has_more ?? metadata?.has_more ?? raw?.next_cursor != null,
    paged: raw != null
  };
}

function normalizeStructurePage(
  raw: ConversationStructureView & Record<string, unknown>,
  selectedCollection?: ConversationCollection
): ConversationStructurePage {
  const collections = [
    "threads",
    "segments",
    "relations",
    "episodes",
    "entities",
    "knowledge_gaps",
    "beliefs",
    "social_events",
    "impressions"
  ] as const;
  const pages = Object.fromEntries(
    collections.map((collection) => {
      const pagination = raw.pagination as Record<string, { next_cursor?: string | null; has_more?: boolean }> | undefined;
      const payload = raw[collection] as CollectionPayload<unknown> | undefined;
      const nested = raw[`${collection}_page`] as
        | { next_cursor?: string | null; has_more?: boolean }
        | undefined;
      const metadata = pagination?.[collection] ?? nested ?? {
        next_cursor: raw[`${collection}_next_cursor`] as string | null | undefined,
        has_more: raw[`${collection}_has_more`] as boolean | undefined
      };
      if (selectedCollection === collection && metadata.next_cursor === undefined && metadata.has_more === undefined) {
        metadata.next_cursor = raw.next_cursor as string | null | undefined;
        metadata.has_more = raw.has_more as boolean | undefined;
      }
      return [collection, collectionPage(payload, metadata)];
    })
  ) as ConversationStructurePages;
  const view = Object.fromEntries(
    collections.map((collection) => [collection, pages[collection].items])
  ) as Omit<ConversationStructureView, "deployment_id">;
  return {
    deployment_id: raw.deployment_id,
    ...view,
    pages
  };
}

export interface ConversationStructureLoadOptions {
  collection?: ConversationCollection;
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}

export async function loadConversationStructurePage(
  deploymentId: string,
  options: ConversationStructureLoadOptions = {}
): Promise<ConversationStructurePage> {
  const query = new URLSearchParams();
  if (options.limit != null) query.set("limit", String(options.limit));
  if (options.collection && options.cursor) {
    query.set(`${options.collection}_cursor`, options.cursor);
  }
  const suffix = query.toString();
  const response = await fetch(
    `/api/deployments/${encodeURIComponent(deploymentId)}/conversation-structure${suffix ? `?${suffix}` : ""}`,
    { credentials: "include", signal: options.signal }
  );
  if (!response.ok) throw new Error(await response.text());
  return normalizeStructurePage(
    (await response.json()) as ConversationStructureView & Record<string, unknown>,
    options.collection
  );
}

export async function loadConversationStructure(
  deploymentId: string
): Promise<ConversationStructureView> {
  const page = await loadConversationStructurePage(deploymentId);
  const { pages: _pages, ...view } = page;
  return view;
}

async function managementRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export function listKnowledgeGapCandidates(deploymentId: string, gapId: string) {
  return managementRequest<{ items: KnowledgeGapCandidate[] }>(
    `/api/deployments/${encodeURIComponent(deploymentId)}/knowledge-gaps/${encodeURIComponent(gapId)}/candidates?include_terminal=false`
  );
}

export function reviewKnowledgeGapCandidate(
  deploymentId: string,
  gapId: string,
  candidateId: string,
  payload: {
    action: "accept" | "reject";
    validated_evidence_ref?: string;
    resolved_fields?: string[];
    confidence?: number;
  }
) {
  return managementRequest<{ gap: KnowledgeGapObservation; candidate: KnowledgeGapCandidate }>(
    `/api/deployments/${encodeURIComponent(deploymentId)}/knowledge-gaps/${encodeURIComponent(gapId)}/candidates/${encodeURIComponent(candidateId)}/review`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function getBeliefDetail(deploymentId: string, beliefId: string) {
  return managementRequest<BeliefDetail>(
    `/api/deployments/${encodeURIComponent(deploymentId)}/beliefs/${encodeURIComponent(beliefId)}`
  );
}

export function correctBelief(
  deploymentId: string,
  beliefId: string,
  payload: { value_text: string; domain: "personal" | "canonical" | "general"; reason: string; confidence?: number }
) {
  return managementRequest<BeliefManagementResult>(
    `/api/deployments/${encodeURIComponent(deploymentId)}/beliefs/${encodeURIComponent(beliefId)}/correct`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

function changeBeliefStatus(deploymentId: string, beliefId: string, action: "reject" | "forget", reason: string) {
  return managementRequest<BeliefManagementResult>(
    `/api/deployments/${encodeURIComponent(deploymentId)}/beliefs/${encodeURIComponent(beliefId)}/${action}`,
    { method: "POST", body: JSON.stringify({ reason }) }
  );
}

export const rejectBelief = (deploymentId: string, beliefId: string, reason: string) =>
  changeBeliefStatus(deploymentId, beliefId, "reject", reason);

export const forgetBelief = (deploymentId: string, beliefId: string, reason: string) =>
  changeBeliefStatus(deploymentId, beliefId, "forget", reason);
