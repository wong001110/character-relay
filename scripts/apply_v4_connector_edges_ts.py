from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:140]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_text(path: str, value: str) -> None:
    target = Path(path)
    target.write_text(target.read_text(encoding="utf-8") + value, encoding="utf-8")


# Runtime config exposes the same lightweight continuation window to the server fallback.
replace_once(
    "connectors/discord/src/config.ts",
    "  smartParticipationMaxRepliesPerWindow: number;\n  smartParticipationTurnCollectorEnabled: boolean;\n",
    "  smartParticipationMaxRepliesPerWindow: number;\n  smartParticipationLightweightFollowUpWindowSeconds: number;\n  smartParticipationTurnCollectorEnabled: boolean;\n",
)
replace_once(
    "connectors/discord/src/config.ts",
    '''    smartParticipationMaxRepliesPerWindow: integer(\n      "DISCORD_SMART_PARTICIPATION_MAX_REPLIES_PER_WINDOW",\n      3,\n      1\n    ),\n    smartParticipationTurnCollectorEnabled: boolean(\n''',
    '''    smartParticipationMaxRepliesPerWindow: integer(\n      "DISCORD_SMART_PARTICIPATION_MAX_REPLIES_PER_WINDOW",\n      3,\n      1\n    ),\n    smartParticipationLightweightFollowUpWindowSeconds: boundedInteger(\n      "DISCORD_SMART_PARTICIPATION_LIGHTWEIGHT_FOLLOW_UP_WINDOW_SECONDS",\n      90,\n      1,\n      600\n    ),\n    smartParticipationTurnCollectorEnabled: boolean(\n''',
)
replace_once(
    "connectors/discord/src/config.ts",
    '''    maxRepliesPerWindow: config.smartParticipationMaxRepliesPerWindow\n  });\n''',
    '''    maxRepliesPerWindow: config.smartParticipationMaxRepliesPerWindow,\n    lightweightFollowUpWindowSeconds:\n      config.smartParticipationLightweightFollowUpWindowSeconds\n  });\n''',
)

# Only pure, directly visible image attachments may enter a Conversation Burst.
replace_once(
    "connectors/discord/src/turnIngress.ts",
    "  attachmentCount: number;\n  embedCount: number;\n",
    "  attachmentCount: number;\n  visibleImageAttachmentCount: number;\n  embedCount: number;\n",
)
replace_once(
    "connectors/discord/src/turnIngress.ts",
    '''  if (\n    input.customEmojiCount > 0 ||\n    input.stickerCount > 0 ||\n    input.attachmentCount > 0 ||\n    input.embedCount > 0\n  ) {\n    return { collect: false, reason: "rich_content" };\n  }\n  if (input.hasUrl) return { collect: false, reason: "url_content" };\n  if (!input.hasReadableText) return { collect: false, reason: "empty_text" };\n''',
    '''  const imageOnlyAttachments =\n    input.attachmentCount > 0 &&\n    input.visibleImageAttachmentCount === input.attachmentCount;\n  if (\n    input.customEmojiCount > 0 ||\n    input.stickerCount > 0 ||\n    input.embedCount > 0 ||\n    (input.attachmentCount > 0 && !imageOnlyAttachments)\n  ) {\n    return { collect: false, reason: "rich_content" };\n  }\n  if (input.hasUrl) return { collect: false, reason: "url_content" };\n  if (!input.hasReadableText && !imageOnlyAttachments) {\n    return { collect: false, reason: "empty_text" };\n  }\n''',
)
replace_once(
    "connectors/discord/src/turnIngress.test.ts",
    "  attachmentCount: 0,\n  embedCount: 0,\n",
    "  attachmentCount: 0,\n  visibleImageAttachmentCount: 0,\n  embedCount: 0,\n",
)
append_text(
    "connectors/discord/src/turnIngress.test.ts",
    '''\n\ndescribe("visible-image Turn Collection policy", () => {\n  it("collects a pure visible image attachment so following text can share one burst", () => {\n    expect(\n      decideTurnCollection({\n        ...basePolicy,\n        hasReadableText: false,\n        attachmentCount: 1,\n        visibleImageAttachmentCount: 1\n      })\n    ).toEqual({ collect: true, reason: "collect" });\n  });\n\n  it("still bypasses mixed or non-image attachments", () => {\n    expect(\n      decideTurnCollection({\n        ...basePolicy,\n        attachmentCount: 2,\n        visibleImageAttachmentCount: 1\n      })\n    ).toEqual({ collect: false, reason: "rich_content" });\n  });\n});\n''',
)

# Preserve burst source image message IDs across the Connector API boundary.
replace_once(
    "connectors/discord/src/types.ts",
    "  stickers: DiscordStickerContent[];\n  available_characters: string[];\n",
    "  stickers: DiscordStickerContent[];\n  burst_media_message_ids?: string[];\n  available_characters: string[];\n",
)

# Server durable recent speaker lookup.
replace_once(
    "connectors/discord/src/relayClient.ts",
    '''  async observeSmartParticipationOutcome(input: {\n''',
    '''  async recentSmartParticipationSpeaker(input: {\n    guild_id: string;\n    channel_id: string;\n    thread_id: string;\n    maximum_age_seconds: number;\n    allowed_deployment_ids: string[];\n  }): Promise<string> {\n    const result = await this.request<{ deployment_id: string }>(\n      "/api/smart-participation/recent-speaker",\n      {\n        method: "POST",\n        body: JSON.stringify({ connection_id: this.connectionId, ...input })\n      }\n    );\n    return result.deployment_id ?? "";\n  }\n\n  async observeSmartParticipationOutcome(input: {\n''',
)

# Rehydrate a server-proven recent speaker through the same local admission machinery.
replace_once(
    "connectors/discord/src/smartParticipation.ts",
    '''export function buildSmartParticipationBaseEvidence(\n''',
    '''export function restoreDurableLightweightSelection(\n  deployments: DiscordDeployment[],\n  deploymentId: string,\n  message: string,\n  now = Date.now(),\n  runtimeScopeKey?: string\n): SmartParticipationDecision {\n  clearPending(deployments);\n  if (!runtimeConfig.enabled) {\n    return decision("disabled", [], [], message.length);\n  }\n  const text = normalizeText(message);\n  if (!text || !isLowInformation(text)) {\n    return decision("low_information_message", [], [], text.length);\n  }\n  const deployment = deployments.find(\n    (item) =>\n      item.participation_mode === "smart" &&\n      item.deployment_id === deploymentId\n  );\n  if (!deployment) {\n    return decision("low_information_message", [], [], text.length);\n  }\n  const candidate = lightweightCandidate(deployment, text);\n  if (!candidate.eligible || candidate.score < candidate.minimumScore) {\n    return decision("low_information_message", [], [candidate], text.length);\n  }\n  queueSelection(deployment, "lightweight", now, runtimeScopeKey);\n  return decision("selected_lightweight", [deployment], [candidate], text.length);\n}\n\nexport function buildSmartParticipationBaseEvidence(\n''',
)
replace_once(
    "connectors/discord/src/smartParticipation.test.ts",
    "  resetSmartParticipationState\n} from \"./smartParticipation.js\";\n",
    "  resetSmartParticipationState,\n  restoreDurableLightweightSelection\n} from \"./smartParticipation.js\";\n",
)
append_text(
    "connectors/discord/src/smartParticipation.test.ts",
    '''\n\ndescribe("durable lightweight recovery", () => {\n  beforeEach(() => {\n    resetSmartParticipationState();\n  });\n\n  it("rehydrates a server-proven recent Smart speaker into the normal local admission path", () => {\n    configure({\n      profiles: {\n        "character-ann": {\n          initiative: 0.3,\n          minimum_score: 5,\n          cooldown_seconds: 0\n        }\n      }\n    });\n    const result = restoreDurableLightweightSelection(\n      [ann, zhi],\n      ann.deployment_id,\n      "真的？",\n      1_000_000,\n      "connection-1:guild-1:channel-1:"\n    );\n\n    expect(result.reason).toBe("selected_lightweight");\n    expect(result.selectedDeployment?.deployment_id).toBe(ann.deployment_id);\n    expect(consumeSmartSelection(ann.deployment_id)).toBe(true);\n    expect(\n      evaluateSmartParticipation(\n        [ann, zhi],\n        "然后呢？",\n        1_001_000,\n        {},\n        "connection-1:guild-1:channel-1:"\n      ).reason\n    ).toBe("low_information_message");\n  });\n\n  it("does not restore a Character blocked by its avoid phrase", () => {\n    configure({\n      profiles: {\n        "character-ann": {\n          avoid_phrases: ["不用回答"],\n          initiative: 0.3,\n          minimum_score: 5,\n          cooldown_seconds: 0\n        }\n      }\n    });\n    const result = restoreDurableLightweightSelection(\n      [ann],\n      ann.deployment_id,\n      "不用回答",\n      1_000_000\n    );\n    expect(result.selectedDeployment).toBeNull();\n  });\n});\n''',
)

# Connector integration: visible-image count/provenance and restart-only durable fallback.
replace_once(
    "connectors/discord/src/index.ts",
    '''  buildSmartParticipationBaseEvidence,\n  preflightSmartParticipationRuntime\n} from "./smartParticipation.js";\n''',
    '''  buildSmartParticipationBaseEvidence,\n  preflightSmartParticipationRuntime,\n  restoreDurableLightweightSelection\n} from "./smartParticipation.js";\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''function log(message: string, metadata?: Record<string, unknown>): void {\n''',
    '''function isVisibleImageAttachment(attachment: {\n  contentType?: string | null;\n  name?: string | null;\n}): boolean {\n  const contentType = attachment.contentType?.trim().toLowerCase() ?? "";\n  if (contentType.startsWith("image/")) return true;\n  const name = attachment.name?.trim().toLowerCase() ?? "";\n  return /\\.(?:png|jpe?g|webp|gif|avif)$/u.test(name);\n}\n\nfunction visibleImageAttachmentCount(message: Message<true>): number {\n  return [...message.attachments.values()].filter(isVisibleImageAttachment).length;\n}\n\nfunction log(message: string, metadata?: Record<string, unknown>): void {\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    const participationBurstId = burstTelemetry?.burstId ?? "";\n    const participationBurstMessages = burst\n''',
    '''    const participationBurstId = burstTelemetry?.burstId ?? "";\n    const burstMediaMessageIds = burst\n      ? [\n          ...new Set(\n            burst.items\n              .slice(0, -1)\n              .filter((item) => {\n                const imageCount = visibleImageAttachmentCount(item.source);\n                return (\n                  imageCount > 0 &&\n                  imageCount === item.source.attachments.size &&\n                  item.source.embeds.length === 0 &&\n                  !/https?:\\/\\//iu.test(item.source.content)\n                );\n              })\n              .map((item) => item.source.id)\n          )\n        ].slice(-2)\n      : [];\n    const participationBurstMessages = burst\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    const semanticScores: Record<string, number> = {};\n    let serverSpeakerPlan: DiscordParticipationShadowPlanItem[] | undefined;\n''',
    '''    const semanticScores: Record<string, number> = {};\n    let semanticPreflightReason = "not_run";\n    let serverSpeakerPlan: DiscordParticipationShadowPlanItem[] | undefined;\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      const semanticPreflight = preflightSmartParticipationRuntime(\n        candidates,\n        participationText,\n        semanticPreflightNow,\n        smartRuntimeScopeKey\n      );\n      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;\n''',
    '''      const semanticPreflight = preflightSmartParticipationRuntime(\n        candidates,\n        participationText,\n        semanticPreflightNow,\n        smartRuntimeScopeKey\n      );\n      semanticPreflightReason = semanticPreflight.reason;\n      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    if (serverSpeakerPlanAuthoritative && !replyTarget.deploymentId) {\n''',
    '''    if (\n      !audience.deployments.length &&\n      !replyTarget.deploymentId &&\n      semanticPreflightReason === "low_information_message"\n    ) {\n      const allowedDeploymentIds = candidates\n        .filter((candidate) => candidate.participation_mode === "smart")\n        .map((candidate) => candidate.deployment_id);\n      if (allowedDeploymentIds.length) {\n        try {\n          const durableDeploymentId = await relay.recentSmartParticipationSpeaker({\n            guild_id: guildMessage.guildId,\n            channel_id: location.channelId,\n            thread_id: location.threadId,\n            maximum_age_seconds:\n              config.smartParticipationLightweightFollowUpWindowSeconds,\n            allowed_deployment_ids: allowedDeploymentIds\n          });\n          if (durableDeploymentId) {\n            const restored = restoreDurableLightweightSelection(\n              candidates,\n              durableDeploymentId,\n              participationText,\n              Date.now(),\n              smartRuntimeScopeKey\n            );\n            if (restored.selectedDeployments.length) {\n              audience = {\n                deployments: restored.selectedDeployments,\n                text: participationText.trim(),\n                reason: "selected_smart",\n                options: audience.options\n              };\n              reportDiscordEvent({\n                level: "info",\n                eventType: "smart_participation_durable_lightweight_recovered",\n                message:\n                  "A low-information Smart Participation turn recovered its recent speaker from durable server state.",\n                guildId: guildMessage.guildId,\n                guildName: guildMessage.guild.name,\n                channelId: location.channelId,\n                channelName: location.channelName,\n                threadId: location.threadId,\n                threadName: location.threadName,\n                sourceMessageId: guildMessage.id,\n                deploymentId: durableDeploymentId,\n                details: { maximum_age_seconds: config.smartParticipationLightweightFollowUpWindowSeconds }\n              });\n            }\n          }\n        } catch (error) {\n          reportDiscordEvent({\n            level: "warning",\n            eventType: "smart_participation_durable_lightweight_failed",\n            message:\n              "Durable recent-speaker recovery failed; local Smart Participation routing remained authoritative.",\n            guildId: guildMessage.guildId,\n            guildName: guildMessage.guild.name,\n            channelId: location.channelId,\n            channelName: location.channelName,\n            threadId: location.threadId,\n            threadName: location.threadName,\n            sourceMessageId: guildMessage.id,\n            details: { error: error instanceof Error ? error.message : String(error) }\n          });\n        }\n      }\n    }\n    if (serverSpeakerPlanAuthoritative && !replyTarget.deploymentId) {\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        stickers: socialSource ? [] : stickers,\n        interaction_session_id: "",\n''',
    '''        stickers: socialSource ? [] : stickers,\n        burst_media_message_ids: socialSource ? [] : burstMediaMessageIds,\n        interaction_session_id: "",\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''  const collectionDecision = decideTurnCollection({\n    collectorEnabled: turnIngress.enabled,\n''',
    '''  const visibleImageCount = visibleImageAttachmentCount(guildMessage);\n  const collectionDecision = decideTurnCollection({\n    collectorEnabled: turnIngress.enabled,\n''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''    attachmentCount: guildMessage.attachments.size,\n    embedCount: guildMessage.embeds.length,\n''',
    '''    attachmentCount: guildMessage.attachments.size,\n    visibleImageAttachmentCount: visibleImageCount,\n    embedCount: guildMessage.embeds.length,\n''',
)
