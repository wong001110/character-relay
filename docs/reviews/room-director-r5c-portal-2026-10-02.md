# R5-C Portal retirement checkpoint

Self-review on the exact R5-B source. Runtime safety and delivery contracts remain unchanged
in this frontend slice. Free Token Pool and authored character settings remain accessible.
New real-data note/catalog APIs replace the former inspection/configuration surfaces.

Checks: Node 24 frontend typecheck; 60 Vitest cases; production build. Browser verification
and integrated backend/Connector validation follow the completed feature. No user data changed.
Old tests below solely prescribe the retired UI/API and are deleted rather than silently skipped.
New note API tests cover scope transport, escaped stable IDs, version conflicts and unsafe error
bodies; existing authorization/source tests remain in the backend.

## Removed paths

- `web/src/ConversationBurstRuntimePanel.tsx`
- `web/src/ConversationIntelligenceInspector.tsx`
- `web/src/ConversationStructurePanel.tsx`
- `web/src/DeploymentDailyRhythmPanel.tsx`
- `web/src/DeploymentDiscoveryPanel.tsx`
- `web/src/DeploymentDiscoverySettings.tsx`
- `web/src/DeploymentDiscoveryWorkspace.tsx`
- `web/src/DeploymentPresencePanel.tsx`
- `web/src/DeploymentRelationshipPanel.tsx`
- `web/src/DiscoveryIntelligencePanel.tsx`
- `web/src/InteractionSessionsPanel.tsx`
- `web/src/ParticipationIntelligencePanel.tsx`
- `web/src/SemanticProfilePanel.tsx`
- `web/src/SemanticRoutingJudgeDock.tsx`
- `web/src/SemanticRoutingJudgePanel.tsx`
- `web/src/SmartParticipationStudio.tsx`
- `web/src/SocialIntelligencePanel.tsx`
- `web/src/conversation-structure.css`
- `web/src/conversationEpisodeBoard.test.ts`
- `web/src/conversationEpisodeBoard.ts`
- `web/src/conversationPagination.test.ts`
- `web/src/conversationPagination.ts`
- `web/src/conversationRelationBoard.test.ts`
- `web/src/conversationRelationBoard.ts`
- `web/src/conversationStructureApi.test.ts`
- `web/src/conversationStructureApi.ts`
- `web/src/conversationThreadMap.test.ts`
- `web/src/conversationThreadMap.ts`
- `web/src/deployment-discovery.css`
- `web/src/deployment-presence.css`
- `web/src/deployment-relationships.css`
- `web/src/deploymentPresenceApi.ts`
- `web/src/discoveryApi.test.ts`
- `web/src/discoveryApi.ts`
- `web/src/intelligenceProductApi.ts`
- `web/src/interaction-scrapbook-v3.css`
- `web/src/interactionApi.ts`
- `web/src/interactionSessions.css`
- `web/src/relationshipApi.ts`
- `web/src/semantic-routing-admin.css`
- `web/src/smartParticipation.css`
- `web/src/smartParticipationApi.ts`
