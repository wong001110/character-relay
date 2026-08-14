from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMART = ROOT / "connectors/discord/src/smartParticipation.ts"
ROUTING = ROOT / "connectors/discord/src/routing.ts"
INDEX = ROOT / "connectors/discord/src/index.ts"
TEST = ROOT / "connectors/discord/src/smartParticipationRuntimePreflight.test.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_smart() -> None:
    text = SMART.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'export interface SmartParticipationDecision {\n'
        '  reason: SmartParticipationReason;\n'
        '  selectedDeployment: DiscordDeployment | null;\n'
        '  selectedDeployments: DiscordDeployment[];\n'
        '  turns: SmartParticipationTurnSelection[];\n'
        '  candidates: SmartParticipationCandidateScore[];\n'
        '}\n\n',
        'export interface SmartParticipationDecision {\n'
        '  reason: SmartParticipationReason;\n'
        '  selectedDeployment: DiscordDeployment | null;\n'
        '  selectedDeployments: DiscordDeployment[];\n'
        '  turns: SmartParticipationTurnSelection[];\n'
        '  candidates: SmartParticipationCandidateScore[];\n'
        '}\n\n'
        'export type SmartParticipationSemanticPreflightReason =\n'
        '  | "semantic_required"\n'
        '  | "disabled"\n'
        '  | "no_smart_candidates"\n'
        '  | "empty_message"\n'
        '  | "low_information_message"\n'
        '  | "channel_cooldown"\n'
        '  | "channel_rate_limit"\n'
        '  | "all_candidates_blocked";\n\n'
        'export interface SmartParticipationSemanticPreflight {\n'
        '  skipSemantic: boolean;\n'
        '  reason: SmartParticipationSemanticPreflightReason;\n'
        '  semanticCandidateDeploymentIds: string[];\n'
        '}\n\n',
        "preflight types",
    )

    text = replace_once(
        text,
        'interface PendingSmartSelection {\n'
        '  deployment: DiscordDeployment;\n'
        '  origin: SmartSelectionOrigin;\n'
        '  selectedAt: number;\n'
        '}\n',
        'interface PendingSmartSelection {\n'
        '  deployment: DiscordDeployment;\n'
        '  origin: SmartSelectionOrigin;\n'
        '  selectedAt: number;\n'
        '  scopeKey: string;\n'
        '}\n',
        "pending selection scope",
    )

    text = replace_once(
        text,
        'function queueSelection(\n'
        '  deployment: DiscordDeployment,\n'
        '  origin: SmartSelectionOrigin,\n'
        '  selectedAt: number\n'
        '): void {\n'
        '  pendingSmartSelections.set(deployment.deployment_id, {\n'
        '    deployment,\n'
        '    origin,\n'
        '    selectedAt\n'
        '  });\n'
        '}\n',
        'function queueSelection(\n'
        '  deployment: DiscordDeployment,\n'
        '  origin: SmartSelectionOrigin,\n'
        '  selectedAt: number,\n'
        '  runtimeScopeKey?: string\n'
        '): void {\n'
        '  pendingSmartSelections.set(deployment.deployment_id, {\n'
        '    deployment,\n'
        '    origin,\n'
        '    selectedAt,\n'
        '    scopeKey: runtimeScopeKey?.trim() || scopeKey(deployment)\n'
        '  });\n'
        '}\n',
        "queue selection scope",
    )

    text = replace_once(
        text,
        'function evaluateLightweightParticipation(\n'
        '  smartCandidates: DiscordDeployment[],\n'
        '  text: string,\n'
        '  now: number\n'
        '): SmartParticipationDecision {\n'
        '  const scope = scopeKey(smartCandidates[0]!);\n',
        'function evaluateLightweightParticipation(\n'
        '  smartCandidates: DiscordDeployment[],\n'
        '  text: string,\n'
        '  now: number,\n'
        '  runtimeScopeKey?: string\n'
        '): SmartParticipationDecision {\n'
        '  const scope = runtimeScopeKey?.trim() || scopeKey(smartCandidates[0]!);\n',
        "lightweight scope",
    )
    text = replace_once(
        text,
        '  queueSelection(deployment, "lightweight", now);\n',
        '  queueSelection(deployment, "lightweight", now, scope);\n',
        "lightweight queue scope",
    )

    marker = 'export function evaluateSmartParticipation(\n'
    if text.count(marker) != 1:
        raise RuntimeError("evaluate marker changed")
    preflight = '''export function preflightSmartParticipationRuntime(
  deployments: DiscordDeployment[],
  message: string,
  now = Date.now(),
  runtimeScopeKey?: string
): SmartParticipationSemanticPreflight {
  if (!runtimeConfig.enabled) {
    return { skipSemantic: true, reason: "disabled", semanticCandidateDeploymentIds: [] };
  }
  const smartCandidates = deployments.filter(
    (deployment) => deployment.participation_mode === "smart"
  );
  if (!smartCandidates.length) {
    return {
      skipSemantic: true,
      reason: "no_smart_candidates",
      semanticCandidateDeploymentIds: []
    };
  }

  const text = normalizeText(message);
  if (!text) {
    return { skipSemantic: true, reason: "empty_message", semanticCandidateDeploymentIds: [] };
  }

  pruneSelections(now);
  if (isLowInformation(text)) {
    return {
      skipSemantic: true,
      reason: "low_information_message",
      semanticCandidateDeploymentIds: []
    };
  }

  const scope = runtimeScopeKey?.trim() || scopeKey(smartCandidates[0]!);
  const scopeSelections = proactiveSelections
    .filter((item) => item.scopeKey === scope)
    .sort((left, right) => right.selectedAt - left.selectedAt);
  const latest = scopeSelections[0];
  if (latest && now - latest.selectedAt < runtimeConfig.channelCooldownSeconds * 1000) {
    return {
      skipSemantic: true,
      reason: "channel_cooldown",
      semanticCandidateDeploymentIds: []
    };
  }

  const windowStart = now - runtimeConfig.windowSeconds * 1000;
  if (
    scopeSelections.filter((item) => item.selectedAt >= windowStart).length >=
    runtimeConfig.maxRepliesPerWindow
  ) {
    return {
      skipSemantic: true,
      reason: "channel_rate_limit",
      semanticCandidateDeploymentIds: []
    };
  }

  const semanticCandidateDeploymentIds = smartCandidates.flatMap((deployment) => {
    const profile = smartParticipationProfileFor(deployment);
    if (!profile.enabled || matchedPhrases(text, profile.avoidPhrases).length) return [];
    const lastSelection = lastSelectionFor(deployment.deployment_id);
    if (lastSelection && now - lastSelection.selectedAt < profile.cooldownSeconds * 1000) {
      return [];
    }
    return [deployment.deployment_id];
  });
  if (!semanticCandidateDeploymentIds.length) {
    return {
      skipSemantic: true,
      reason: "all_candidates_blocked",
      semanticCandidateDeploymentIds: []
    };
  }
  return {
    skipSemantic: false,
    reason: "semantic_required",
    semanticCandidateDeploymentIds
  };
}

'''
    text = text.replace(marker, preflight + marker, 1)

    text = replace_once(
        text,
        'export function evaluateSmartParticipation(\n'
        '  deployments: DiscordDeployment[],\n'
        '  message: string,\n'
        '  now = Date.now(),\n'
        '  semanticScores: SmartParticipationSemanticScores = {}\n'
        '): SmartParticipationDecision {\n',
        'export function evaluateSmartParticipation(\n'
        '  deployments: DiscordDeployment[],\n'
        '  message: string,\n'
        '  now = Date.now(),\n'
        '  semanticScores: SmartParticipationSemanticScores = {},\n'
        '  runtimeScopeKey?: string\n'
        '): SmartParticipationDecision {\n',
        "evaluate signature scope",
    )
    text = replace_once(
        text,
        '    return evaluateLightweightParticipation(smartCandidates, text, now);\n',
        '    return evaluateLightweightParticipation(smartCandidates, text, now, runtimeScopeKey);\n',
        "evaluate lightweight scope",
    )
    text = replace_once(
        text,
        '  const scope = scopeKey(smartCandidates[0]!);\n'
        '  const scopeSelections = proactiveSelections\n',
        '  const scope = runtimeScopeKey?.trim() || scopeKey(smartCandidates[0]!);\n'
        '  const scopeSelections = proactiveSelections\n',
        "evaluate channel scope",
    )
    text = replace_once(
        text,
        '    queueSelection(deployment, "proactive", now);\n',
        '    queueSelection(deployment, "proactive", now, scope);\n',
        "evaluate proactive queue scope",
    )

    text = replace_once(
        text,
        'export function coordinateExplicitSmartParticipants(\n'
        '  deployments: DiscordDeployment[],\n'
        '  explicitDeployments: DiscordDeployment[],\n'
        '  message: string,\n'
        '  now = Date.now(),\n'
        '  semanticScores: SmartParticipationSemanticScores = {}\n'
        '): ExplicitParticipationCoordination {\n',
        'export function coordinateExplicitSmartParticipants(\n'
        '  deployments: DiscordDeployment[],\n'
        '  explicitDeployments: DiscordDeployment[],\n'
        '  message: string,\n'
        '  now = Date.now(),\n'
        '  semanticScores: SmartParticipationSemanticScores = {},\n'
        '  runtimeScopeKey?: string\n'
        '): ExplicitParticipationCoordination {\n',
        "coordinate signature scope",
    )
    text = replace_once(
        text,
        '    markExplicitSmartSelections(explicitDeployments, now);\n',
        '    markExplicitSmartSelections(explicitDeployments, now, runtimeScopeKey);\n',
        "coordinate fallback mark scope",
    )
    text = replace_once(
        text,
        '  queueSelection(primary, "explicit", now);\n',
        '  queueSelection(primary, "explicit", now, runtimeScopeKey);\n',
        "coordinate primary scope",
    )
    text = replace_once(
        text,
        '  queueSelection(interject, "proactive", now);\n',
        '  queueSelection(interject, "proactive", now, runtimeScopeKey);\n',
        "coordinate interject scope",
    )

    text = replace_once(
        text,
        'export function markExplicitSmartSelections(\n'
        '  deployments: DiscordDeployment[],\n'
        '  now = Date.now()\n'
        '): void {\n',
        'export function markExplicitSmartSelections(\n'
        '  deployments: DiscordDeployment[],\n'
        '  now = Date.now(),\n'
        '  runtimeScopeKey?: string\n'
        '): void {\n',
        "mark explicit signature",
    )
    text = replace_once(
        text,
        '      queueSelection(deployment, "explicit", now);\n',
        '      queueSelection(deployment, "explicit", now, runtimeScopeKey);\n',
        "mark explicit queue scope",
    )
    text = replace_once(
        text,
        '  const admittedAt = pending.selectedAt;\n'
        '  const scope = scopeKey(pending.deployment);\n',
        '  const admittedAt = pending.selectedAt;\n'
        '  const scope = pending.scopeKey;\n',
        "consume pending scope",
    )

    SMART.write_text(text, encoding="utf-8")


def patch_routing() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'export function resolveAudience(\n'
        '  candidates: DiscordDeployment[],\n'
        '  text: string,\n'
        '  replyDeploymentId?: string | null,\n'
        '  additionalGroupAliases: string[] = [],\n'
        '  semanticScores: SmartParticipationSemanticScores = {}\n'
        '): AudienceResolution {\n',
        'export function resolveAudience(\n'
        '  candidates: DiscordDeployment[],\n'
        '  text: string,\n'
        '  replyDeploymentId?: string | null,\n'
        '  additionalGroupAliases: string[] = [],\n'
        '  semanticScores: SmartParticipationSemanticScores = {},\n'
        '  runtimeScopeKey?: string\n'
        '): AudienceResolution {\n',
        "resolve audience signature",
    )
    text = replace_once(
        text,
        '      markExplicitSmartSelections([replyTarget]);\n',
        '      markExplicitSmartSelections([replyTarget], Date.now(), runtimeScopeKey);\n',
        "reply explicit scope",
    )
    text = replace_once(
        text,
        '    markExplicitSmartSelections(candidates);\n',
        '    markExplicitSmartSelections(candidates, Date.now(), runtimeScopeKey);\n',
        "group explicit scope",
    )
    text = replace_once(
        text,
        '        Date.now(),\n'
        '        semanticScores\n'
        '      );\n',
        '        Date.now(),\n'
        '        semanticScores,\n'
        '        runtimeScopeKey\n'
        '      );\n',
        "coordinate runtime scope",
    )
    text = replace_once(
        text,
        '    markExplicitSmartSelections(named.deployments);\n',
        '    markExplicitSmartSelections(named.deployments, Date.now(), runtimeScopeKey);\n',
        "named explicit scope",
    )
    text = replace_once(
        text,
        '  const smartDecision = evaluateSmartParticipation(candidates, text, Date.now(), semanticScores);\n',
        '  const smartDecision = evaluateSmartParticipation(\n'
        '    candidates,\n'
        '    text,\n'
        '    Date.now(),\n'
        '    semanticScores,\n'
        '    runtimeScopeKey\n'
        '  );\n',
        "smart evaluation runtime scope",
    )
    ROUTING.write_text(text, encoding="utf-8")


def patch_index() -> None:
    text = INDEX.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'import {\n'
        '  buildMentionableParticipants,\n',
        'import { preflightSmartParticipationRuntime } from "./smartParticipation.js";\n'
        'import {\n'
        '  buildMentionableParticipants,\n',
        "index runtime preflight import",
    )

    text = replace_once(
        text,
        '    const semanticScores: Record<string, number> = {};\n'
        '    if (\n',
        '    const semanticScores: Record<string, number> = {};\n'
        '    const smartRuntimeScopeKey = [\n'
        '      config.relayConnectionId,\n'
        '      guildMessage.guildId,\n'
        '      location.channelId,\n'
        '      location.threadId\n'
        '    ].join(":");\n'
        '    if (\n',
        "index runtime scope key",
    )

    old = '''      const smartDeploymentIds = candidates
        .filter((item) => item.participation_mode === "smart")
        .map((item) => item.deployment_id);
      if (smartDeploymentIds.length) {
        try {
          const semantic = await relay.scoreSmartParticipation({
            message: participationText,
            deployment_ids: smartDeploymentIds,
'''
    new = '''      const semanticPreflight = preflightSmartParticipationRuntime(
        candidates,
        participationText,
        Date.now(),
        smartRuntimeScopeKey
      );
      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;
      if (!semanticPreflight.skipSemantic && smartDeploymentIds.length) {
        try {
          const semantic = await relay.scoreSmartParticipation({
            message: participationText,
            deployment_ids: smartDeploymentIds,
'''
    text = replace_once(text, old, new, "index semantic preflight")

    text = replace_once(
        text,
        '              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        '              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null,\n'
        '              semantic_preflight_reason: semanticPreflight.reason,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        "semantic event preflight reason",
    )

    text = replace_once(
        text,
        '        } catch (error) {\n'
        '          reportDiscordEvent({\n'
        '            level: "warning",\n'
        '            eventType: "smart_participation_semantic_failed",\n',
        '        } catch (error) {\n'
        '          reportDiscordEvent({\n'
        '            level: "warning",\n'
        '            eventType: "smart_participation_semantic_failed",\n',
        "semantic catch stable marker",
    )

    text = replace_once(
        text,
        '        }\n'
        '      }\n'
        '    }\n\n'
        '    const audience = resolveAudience(\n',
        '        }\n'
        '      } else if (semanticPreflight.skipSemantic) {\n'
        '        reportDiscordEvent({\n'
        '          level: "info",\n'
        '          eventType: "smart_participation_semantic_skipped",\n'
        '          message: "Runtime state resolved Smart Participation before E5 was needed.",\n'
        '          guildId: guildMessage.guildId,\n'
        '          guildName: guildMessage.guild.name,\n'
        '          channelId: location.channelId,\n'
        '          channelName: location.channelName,\n'
        '          threadId: location.threadId,\n'
        '          threadName: location.threadName,\n'
        '          sourceMessageId: guildMessage.id,\n'
        '          details: {\n'
        '            reason: semanticPreflight.reason,\n'
        '            burst_id: burstTelemetry?.burstId ?? null,\n'
        '            burst_message_count: burstTelemetry?.messageCount ?? 1,\n'
        '            collapsed_message_count: burstTelemetry?.collapsedMessageCount ?? 0\n'
        '          }\n'
        '        });\n'
        '      }\n'
        '    }\n\n'
        '    const audience = resolveAudience(\n',
        "semantic skip event",
    )

    text = replace_once(
        text,
        '      config.groupAddressAliases,\n'
        '      semanticScores\n'
        '    );\n',
        '      config.groupAddressAliases,\n'
        '      semanticScores,\n'
        '      smartRuntimeScopeKey\n'
        '    );\n',
        "resolve audience runtime scope",
    )

    INDEX.write_text(text, encoding="utf-8")


def write_test() -> None:
    TEST.write_text(
        '''import { afterEach, describe, expect, it } from "vitest";\n\nimport {\n  configureSmartParticipation,\n  consumeSmartSelection,\n  evaluateSmartParticipation,\n  preflightSmartParticipationRuntime,\n  resetSmartParticipationState\n} from "./smartParticipation.js";\nimport type { DiscordDeployment } from "./types.js";\n\nfunction deployment(name: string): DiscordDeployment {\n  return {\n    deployment_id: `deployment-${name}`,\n    connection_id: "connection-1",\n    character_card_id: `card-${name}`,\n    character_display_name: name,\n    workspace_id: "guild-1",\n    workspace_name: "Guild",\n    channel_id: "server-wide-template",\n    channel_name: "all except",\n    thread_id: "",\n    thread_name: "",\n    category_id: "",\n    server_profile_id: "profile-1",\n    channel_scope_mode: "all_except",\n    excluded_channel_ids: [],\n    excluded_category_ids: [],\n    participation_mode: "smart",\n    version_label: "Current",\n    status: "active",\n    identity_mode: "webhook",\n    identity_display_name: name,\n    identity_avatar_url: "",\n    address_aliases: [name],\n    webhook_status: "pending",\n    webhook_id: null,\n    webhook_token: null,\n    orchestration_mode: "off"\n  };\n}\n\nfunction scope(channel: string): string {\n  return ["connection-1", "guild-1", channel, ""].join(":");\n}\n\ndescribe("Smart Participation runtime preflight", () => {\n  afterEach(() => {\n    resetSmartParticipationState();\n  });\n\n  it("skips E5 for low-information turns that the existing runtime resolves without semantics", () => {\n    const ann = deployment("Ann");\n    configureSmartParticipation({ enabled: true });\n\n    expect(preflightSmartParticipationRuntime([ann], "嗯", 1_000, scope("general"))).toEqual({\n      skipSemantic: true,\n      reason: "low_information_message",\n      semanticCandidateDeploymentIds: []\n    });\n  });\n\n  it("uses the actual runtime channel scope for server-wide cooldown state", () => {\n    const ann = deployment("Ann");\n    configureSmartParticipation({\n      enabled: true,\n      channelCooldownSeconds: 45,\n      maxRepliesPerWindow: 3,\n      profiles: {\n        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 0 }\n      }\n    });\n\n    const selected = evaluateSmartParticipation(\n      [ann],\n      "photography workflow",\n      1_000,\n      { [ann.deployment_id]: 0.9 },\n      scope("channel-a")\n    );\n    expect(selected.selectedDeployment?.deployment_id).toBe(ann.deployment_id);\n    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);\n\n    expect(\n      preflightSmartParticipationRuntime([ann], "another topic", 2_000, scope("channel-a")).reason\n    ).toBe("channel_cooldown");\n    expect(\n      preflightSmartParticipationRuntime([ann], "another topic", 2_000, scope("channel-b"))\n    ).toEqual({\n      skipSemantic: false,\n      reason: "semantic_required",\n      semanticCandidateDeploymentIds: [ann.deployment_id]\n    });\n  });\n\n  it("skips E5 when the current channel has reached the proactive reply window limit", () => {\n    const ann = deployment("Ann");\n    configureSmartParticipation({\n      enabled: true,\n      channelCooldownSeconds: 0,\n      windowSeconds: 600,\n      maxRepliesPerWindow: 1,\n      profiles: {\n        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 0 }\n      }\n    });\n\n    evaluateSmartParticipation(\n      [ann],\n      "photography workflow",\n      1_000,\n      { [ann.deployment_id]: 0.9 },\n      scope("channel-a")\n    );\n    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);\n\n    expect(\n      preflightSmartParticipationRuntime([ann], "new question", 2_000, scope("channel-a")).reason\n    ).toBe("channel_rate_limit");\n  });\n\n  it("removes only cooldown-blocked characters from semantic candidates", () => {\n    const ann = deployment("Ann");\n    const ning = deployment("Ning");\n    configureSmartParticipation({\n      enabled: true,\n      channelCooldownSeconds: 0,\n      maxRepliesPerWindow: 3,\n      profiles: {\n        [ann.deployment_id]: { style: "balanced", cooldown_seconds: 120 },\n        [ning.deployment_id]: { style: "balanced", cooldown_seconds: 0 }\n      }\n    });\n\n    evaluateSmartParticipation(\n      [ann],\n      "photography workflow",\n      1_000,\n      { [ann.deployment_id]: 0.9 },\n      scope("channel-a")\n    );\n    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);\n\n    expect(\n      preflightSmartParticipationRuntime(\n        [ann, ning],\n        "another unrelated discussion",\n        2_000,\n        scope("channel-b")\n      )\n    ).toEqual({\n      skipSemantic: false,\n      reason: "semantic_required",\n      semanticCandidateDeploymentIds: [ning.deployment_id]\n    });\n  });\n});\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_smart()
    patch_routing()
    patch_index()
    write_test()
