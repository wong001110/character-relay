import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ConversationStructurePanel } from "./ConversationStructurePanel";
import type { ConversationStructureView } from "./conversationStructureApi";
import type { CharacterDeployment } from "./deploymentApi";
import {
  deploymentRouteForPath,
  deploymentRoutes,
  type DeploymentNotebookTab
} from "./portalRoutes";

const mockProfileId = "mock-server-profile";

const mockDeployment: CharacterDeployment = {
  id: "mock-deployment-zhi",
  character_card_id: "mock-character-zhi",
  character_display_name: "織 / Zhi",
  connection_id: "mock-connection",
  platform: "discord",
  server_profile_id: mockProfileId,
  server_profile_name: "Mock Garden Server",
  channel_scope_mode: "all_except",
  excluded_channel_ids: [],
  excluded_category_ids: [],
  workspace_id: "mock-guild",
  workspace_name: "Mock Garden Server",
  channel_id: "mock-channel",
  channel_name: "general",
  thread_id: "",
  thread_name: "",
  participation_mode: "smart",
  memory_scope: "server_shared",
  version_label: "mock-preview",
  sticker_count: 0,
  status: "active",
  last_message_at: "2026-08-23T12:00:00+00:00",
  last_error: "",
  created_at: "2026-08-23T12:00:00+00:00",
  updated_at: "2026-08-23T12:00:00+00:00"
};

const mockConversation: ConversationStructureView = {
  deployment_id: mockDeployment.id,
  threads: Array.from({ length: 10 }, (_, index) => ({
    id: `mock-thread-${index + 1}`,
    canonical_label: `Mock discussion line ${index + 1}`,
    anchor_summary: "A concise, local-only thread summary for layout review.",
    working_summary: `The group is considering mock direction ${index + 1}.`,
    representative_segment_ids: [`mock-segment-${index + 1}`],
    participant_ids: index % 2 === 0 ? ["mock-person-1", "mock-person-2"] : ["mock-person-1"],
    active_entity_ids: [],
    status: index < 3 ? "active" : "dormant",
    last_active_at: `2026-08-23T${String(12 - Math.min(index, 9)).padStart(2, "0")}:00:00+00:00`
  })),
  segments: Array.from({ length: 10 }, (_, index) => ({
    id: `mock-segment-${index + 1}`,
    burst_id: "mock-burst",
    message_ids: [`mock-message-${index + 1}`],
    participant_ids: ["mock-person-1"],
    kind: "discussion",
    summary: `A compact mock segment attached to discussion line ${index + 1}.`,
    thread_id: `mock-thread-${index + 1}`,
    membership_relation: "belongs_to",
    membership_confidence: 0.92,
    confidence: 0.88,
    source: "mock-fixture",
    created_at: "2026-08-23T12:00:00+00:00"
  })),
  relations: Array.from({ length: 13 }, (_, index) => ({
    id: `mock-relation-${index + 1}`,
    source_message_id: `mock-message-source-${index + 1}`,
    source_author_id: `mock-person-${(index % 3) + 1}`,
    source_author_display_name: ["Mina", "Zhi", "Rin"][index % 3] ?? "",
    relation_class: "interaction",
    relation_type: "REPLY_TO",
    target_ref_type: "message",
    target_ref: `mock-message-target-${index + 1}`,
    target_author_id: `mock-person-${((index + 1) % 3) + 1}`,
    target_author_display_name: ["Zhi", "Rin", "Mina"][index % 3] ?? "",
    confidence: 1,
    source: "discord_explicit",
    evidence_refs: [`mock-message-source-${index + 1}`, `mock-message-target-${index + 1}`],
    status: "resolved",
    supersedes_relation_id: "",
    created_at: `2026-08-23T${String(12 - Math.min(index, 9)).padStart(2, "0")}:30:00+00:00`
  })),
  episodes: [
    {
      id: "mock-episode-1",
      conversation_thread_id: "mock-thread-1",
      segment_ids: ["mock-segment-1"],
      source_message_ids: ["mock-message-1", "mock-message-2"],
      participant_ids: ["mock-person-1", "mock-person-2"],
      entity_ids: [],
      media_refs: [],
      summary: "A concise mock conversation event with https://example.invalid/long-link-that-never-becomes-a-note-title",
      key_events: ["A participant shared an idea.", "The group compared two approaches."],
      status: "closed",
      checkpoint_reason: "thread_checkpoint",
      ended_at: "2026-08-23T12:00:00+00:00"
    },
    {
      id: "mock-fragment-1",
      conversation_thread_id: "",
      segment_ids: ["mock-segment-fragment"],
      source_message_ids: ["mock-message-fragment"],
      participant_ids: ["mock-person-1"],
      entity_ids: [],
      media_refs: [],
      summary: "A mock unresolved fragment, kept separate until it belongs to a conversation thread.",
      key_events: [],
      status: "closed",
      checkpoint_reason: "unresolved_segment",
      ended_at: "2026-08-23T11:56:00+00:00"
    },
    ...Array.from({ length: 12 }, (_, index) => ({
      id: `mock-episode-${index + 2}`,
      conversation_thread_id: `mock-thread-${(index % 10) + 1}`,
      segment_ids: [`mock-segment-${(index % 10) + 1}`],
      source_message_ids: [`mock-message-${index + 3}`],
      participant_ids: ["mock-person-1", "mock-person-2"],
      entity_ids: [],
      media_refs: [],
      summary: `A local-only mock episode ${index + 2} used to review board pagination.`,
      key_events: [],
      status: "closed",
      checkpoint_reason: "thread_checkpoint",
      ended_at: `2026-08-23T${String(10 - Math.min(index, 9)).padStart(2, "0")}:00:00+00:00`
    }))
  ],
  entities: [],
  knowledge_gaps: [],
  beliefs: [],
  social_events: [],
  impressions: []
};

function notebookPath(tab: DeploymentNotebookTab): string {
  return tab === "intelligence"
    ? deploymentRoutes.intelligence(mockProfileId, "conversation")
    : deploymentRoutes.notebook(mockProfileId, tab);
}

export function MockDeploymentWorkspace() {
  const location = useLocation();
  const navigate = useNavigate();
  const route = deploymentRouteForPath(location.pathname);
  const tab = route?.notebookTab ?? "characters";

  useEffect(() => {
    if (!route?.serverProfileId) navigate(notebookPath("characters"), { replace: true });
  }, [navigate, route?.serverProfileId]);

  return (
    <main className="deployment-workspace deployment-workspace-mock">
      <header className="deployment-workspace-header paper-sheet">
        <div><span className="tape-label">MOCK SERVER NOTEBOOK</span><h1>Mock Garden Server</h1><p>Local typed fixtures only. No live API requests or mutations are available in this mode.</p></div>
      </header>
      <nav className="server-notebook-tabs" aria-label="Mock Server notebook pages">
        {(["characters", "knowledge", "interactions", "intelligence"] as DeploymentNotebookTab[]).map((item) => <button type="button" key={item} className={tab === item ? "is-active" : ""} onClick={() => navigate(notebookPath(item))}><strong>{item}</strong></button>)}
      </nav>
      {tab === "intelligence" ? <ConversationStructurePanel deployments={[mockDeployment]} zh={false} fixture={mockConversation} /> : <section className="server-notebook-empty paper-sheet"><strong>{tab}</strong><p>This mock preview currently supplies the Server Notebook shell and Conversation Board fixture. Other business pages remain intentionally inert.</p></section>}
    </main>
  );
}
