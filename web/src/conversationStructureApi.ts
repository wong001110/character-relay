export interface SemanticThreadObservation {
  id: string;
  label: string;
  summary: string;
  keywords: string[];
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
  semantic_thread_id: string;
  thread_action: string;
  thread_evidence: boolean;
  confidence: number;
  source: string;
  created_at: string;
}

export interface ConversationStructureView {
  deployment_id: string;
  threads: SemanticThreadObservation[];
  segments: ConversationSegmentObservation[];
}

export async function loadConversationStructure(deploymentId: string): Promise<ConversationStructureView> {
  const response = await fetch(
    `/api/deployments/${encodeURIComponent(deploymentId)}/conversation-structure`,
    { credentials: "include" }
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<ConversationStructureView>;
}
