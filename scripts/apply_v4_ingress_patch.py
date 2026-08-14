from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "connectors/discord/src/index.ts"
RELAY = ROOT / "connectors/discord/src/relayClient.ts"
BURST_TEST = ROOT / "connectors/discord/src/relayClientBurst.test.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    value, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return value


def patch_index() -> None:
    text = INDEX.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'import { loadConfig } from "./config.js";\n',
        'import { resolveExplicitAudiencePreflight } from "./audiencePreflight.js";\n'
        'import { loadConfig } from "./config.js";\n',
        "index audience preflight import",
    )
    text = replace_once(
        text,
        'import { DiscordWebhookManager } from "./webhookManager.js";\n',
        'import type { ConversationBurst } from "./turnCollector.js";\n'
        'import {\n'
        '  TurnIngressCoordinator,\n'
        '  buildConversationBurstId,\n'
        '  buildConversationBurstText,\n'
        '  decideTurnCollection\n'
        '} from "./turnIngress.js";\n'
        'import { DiscordWebhookManager } from "./webhookManager.js";\n',
        "index turn ingress import",
    )

    text = replace_once(
        text,
        'const context = new ContextBuffer(config.maxContextMessages);\n'
        'const queues = new Map<string, Promise<void>>();\n',
        'interface CollectedDiscordTurn {\n'
        '  source: Message<true>;\n'
        '  originalText: string;\n'
        '  authorDisplayName: string;\n'
        '}\n\n'
        'const context = new ContextBuffer(config.maxContextMessages);\n'
        'const queues = new Map<string, Promise<void>>();\n',
        "index collected turn interface",
    )
    text = replace_once(
        text,
        'let lastGatewayMentionedBot = false;\n\n'
        'const catalogChannelTypes = new Set<ChannelType>([\n',
        'let lastGatewayMentionedBot = false;\n'
        'const turnIngress = new TurnIngressCoordinator<CollectedDiscordTurn>(\n'
        '  {\n'
        '    enabled: config.smartParticipationTurnCollectorEnabled,\n'
        '    quietWindowMs: config.smartParticipationTurnCollectorQuietMs,\n'
        '    maxWaitMs: config.smartParticipationTurnCollectorMaxWaitMs,\n'
        '    maxMessages: config.smartParticipationTurnCollectorMaxMessages,\n'
        '    maxCharacters: config.smartParticipationTurnCollectorMaxCharacters\n'
        '  },\n'
        '  enqueue,\n'
        '  (error, scopeKey) => {\n'
        '    lastError = error instanceof Error ? error.message : String(error);\n'
        '    log("Discord Turn Collector ingress failed.", { scopeKey, error: lastError });\n'
        '  }\n'
        ');\n\n'
        'const catalogChannelTypes = new Set<ChannelType>([\n',
        "index turn ingress instance",
    )

    text = replace_once(
        text,
        '  enqueue(key, async () => {\n'
        '    const [emojis, stickers] = await Promise.all([\n',
        '  const collectedTurn: CollectedDiscordTurn = {\n'
        '    source: guildMessage,\n'
        '    originalText,\n'
        '    authorDisplayName\n'
        '  };\n'
        '  const executeQueued = async (\n'
        '    burst: ConversationBurst<CollectedDiscordTurn> | null,\n'
        '    interactionClaimOverride: DiscordInteractionClaim | null\n'
        '  ): Promise<void> => {\n'
        '    if (burst) {\n'
        '      for (const item of burst.items.slice(0, -1)) {\n'
        '        context.push(key, {\n'
        '          message_id: item.source.id,\n'
        '          author_id: item.source.author.id,\n'
        '          author_display_name: item.authorDisplayName,\n'
        '          text: item.originalText,\n'
        '          emojis: [],\n'
        '          stickers: [],\n'
        '          created_at: item.source.createdAt.toISOString(),\n'
        '          is_bot: false\n'
        '        });\n'
        '      }\n'
        '    }\n'
        '    const [emojis, stickers] = await Promise.all([\n',
        "index queued closure start",
    )

    text = replace_once(
        text,
        '    context.push(key, contextMessage);\n\n'
        '    let interactionClaim: DiscordInteractionClaim = {\n',
        '    context.push(key, contextMessage);\n\n'
        '    const participationText = burst\n'
        '      ? buildConversationBurstText(\n'
        '          burst.items.map((item) => ({ text: item.originalText })),\n'
        '          4_000\n'
        '        )\n'
        '      : originalText;\n'
        '    const participationBurstId = burst ? buildConversationBurstId(burst.itemIds) : "";\n'
        '    const participationBurstMessages = burst\n'
        '      ? burst.items.map((item) => ({\n'
        '          message_id: item.source.id,\n'
        '          author_id: item.source.author.id,\n'
        '          author_display_name: item.authorDisplayName,\n'
        '          text: item.originalText,\n'
        '          created_at: item.source.createdAt.toISOString(),\n'
        '          reply_to_message_id: item.source.reference?.messageId ?? ""\n'
        '        }))\n'
        '      : [];\n\n'
        '    let interactionClaim: DiscordInteractionClaim = interactionClaimOverride ?? {\n',
        "index burst analysis variables",
    )

    interaction_pattern = re.escape(
        '    let interactionClaim: DiscordInteractionClaim = interactionClaimOverride ?? {\n'
        '      claimed: false,\n'
        '      run_id: null,\n'
        '      session: null\n'
        '    };\n'
    ) + r'''    try \{\n      interactionClaim = await relay\.claimInteraction\(\{\n        guild_id: guildMessage\.guildId,\n        channel_id: location\.channelId,\n        target_user_id: guildMessage\.author\.id,\n        source_message_id: guildMessage\.id\n      \}\);\n    \} catch \(error\) \{\n      log\("Unable to check Interaction Sessions; continuing normal routing\.", \{\n        guildId: guildMessage\.guildId,\n        channelId: location\.channelId,\n        sourceMessageId: guildMessage\.id,\n        error: error instanceof Error \? error\.message : String\(error\)\n      \}\);\n    \}\n'''
    interaction_replacement = (
        '    let interactionClaim: DiscordInteractionClaim = interactionClaimOverride ?? {\n'
        '      claimed: false,\n'
        '      run_id: null,\n'
        '      session: null\n'
        '    };\n'
        '    if (!interactionClaimOverride) {\n'
        '      try {\n'
        '        interactionClaim = await relay.claimInteraction({\n'
        '          guild_id: guildMessage.guildId,\n'
        '          channel_id: location.channelId,\n'
        '          target_user_id: guildMessage.author.id,\n'
        '          source_message_id: guildMessage.id\n'
        '        });\n'
        '      } catch (error) {\n'
        '        log("Unable to check Interaction Sessions; continuing normal routing.", {\n'
        '          guildId: guildMessage.guildId,\n'
        '          channelId: location.channelId,\n'
        '          sourceMessageId: guildMessage.id,\n'
        '          error: error instanceof Error ? error.message : String(error)\n'
        '        });\n'
        '      }\n'
        '    }\n'
    )
    text = replace_regex_once(
        text,
        interaction_pattern,
        interaction_replacement,
        "index interaction override",
    )

    text = replace_once(
        text,
        '      !replyTarget.deploymentId &&\n'
        '      originalText.trim()\n',
        '      !replyTarget.deploymentId &&\n'
        '      participationText.trim()\n',
        "index semantic participation text condition",
    )
    text = replace_once(
        text,
        '          const semantic = await relay.scoreSmartParticipation({\n'
        '            message: originalText,\n'
        '            deployment_ids: smartDeploymentIds\n'
        '          });\n',
        '          const semantic = await relay.scoreSmartParticipation({\n'
        '            message: participationText,\n'
        '            deployment_ids: smartDeploymentIds,\n'
        '            guild_id: guildMessage.guildId,\n'
        '            channel_id: location.channelId,\n'
        '            thread_id: location.threadId,\n'
        '            message_id: guildMessage.id,\n'
        '            author_id: guildMessage.author.id,\n'
        '            reply_to_message_id: guildMessage.reference?.messageId ?? "",\n'
        '            burst_id: participationBurstId,\n'
        '            burst_messages: participationBurstMessages\n'
        '          });\n',
        "index resolver burst payload",
    )
    text = replace_once(
        text,
        '    const audience = resolveAudience(\n'
        '      candidates,\n'
        '      originalText,\n'
        '      replyTarget.deploymentId,\n',
        '    const audience = resolveAudience(\n'
        '      candidates,\n'
        '      participationText,\n'
        '      replyTarget.deploymentId,\n',
        "index audience burst text",
    )
    text = replace_once(
        text,
        '      const sourceDisplayName = sourceDeployment\n'
        '        ? deploymentDisplayName(sourceDeployment)\n'
        '        : authorDisplayName;\n'
        '      const turnText = socialSource\n',
        '      const sourceDisplayName = sourceDeployment\n'
        '        ? deploymentDisplayName(sourceDeployment)\n'
        '        : authorDisplayName;\n'
        '      const smartParticipationAudience =\n'
        '        audience.reason === "selected_smart" ||\n'
        '        audience.reason === "selected_smart_multiple";\n'
        '      const turnText = socialSource\n',
        "index smart audience turn marker",
    )
    text = replace_once(
        text,
        '        : (addressedToMultiple ? originalText : audience.text) ||\n'
        '          originalText ||\n',
        '        : (smartParticipationAudience\n'
        '            ? originalText\n'
        '            : addressedToMultiple\n'
        '              ? originalText\n'
        '              : audience.text) ||\n'
        '          originalText ||\n',
        "index preserve latest character turn text",
    )

    resume_marker = "\nasync function resumePendingSocialTurns(): Promise<void> {"
    resume_index = text.find(resume_marker)
    if resume_index < 0:
        raise RuntimeError("index resume marker not found")
    prefix = text[:resume_index]
    suffix = text[resume_index:]
    closing = "    }\n  });\n}\n"
    if not prefix.endswith(closing):
        raise RuntimeError("index processMessage closing shape changed")
    prefix = prefix[: -len(closing)]
    scheduling = '''    }\n  };\n\n  const explicitAudience = resolveExplicitAudiencePreflight(\n    candidates,\n    originalText,\n    null,\n    config.groupAddressAliases\n  );\n  const customEmojiCount = parseCustomEmojiTokens(guildMessage.content).length;\n  const smartCandidateCount = candidates.filter(\n    (item) => item.participation_mode === "smart"\n  ).length;\n  const collectionDecision = decideTurnCollection({\n    collectorEnabled: turnIngress.enabled,\n    smartParticipationEnabled: config.smartParticipationEnabled,\n    recovery: Boolean(options?.recovery),\n    mentionedBot,\n    hasReplyReference: Boolean(guildMessage.reference?.messageId),\n    explicitAudience: Boolean(explicitAudience),\n    hasReadableText: Boolean(originalText.trim()),\n    customEmojiCount,\n    stickerCount: guildMessage.stickers.size,\n    attachmentCount: guildMessage.attachments.size,\n    embedCount: guildMessage.embeds.length,\n    hasUrl: /https?:\\/\\//iu.test(guildMessage.content),\n    smartCandidateCount\n  });\n  let preclaimedInteraction: DiscordInteractionClaim | null = null;\n\n  if (collectionDecision.collect) {\n    log("Smart Participation message entered the Turn Collector.", {\n      guildId: guildMessage.guildId,\n      channelId: location.channelId,\n      threadId: location.threadId || null,\n      sourceMessageId: guildMessage.id,\n      pendingBurstScopes: turnIngress.pendingBurstScopeCount,\n      quietWindowMs: config.smartParticipationTurnCollectorQuietMs\n    });\n  }\n\n  turnIngress.submit(key, {\n    id: guildMessage.id,\n    value: collectedTurn,\n    characters: originalText.length,\n    receivedAt: guildMessage.createdTimestamp,\n    collect: collectionDecision.collect,\n    prepareCollection: collectionDecision.collect\n      ? async () => {\n          try {\n            const claim = await relay.claimInteraction({\n              guild_id: guildMessage.guildId,\n              channel_id: location.channelId,\n              target_user_id: guildMessage.author.id,\n              source_message_id: guildMessage.id\n            });\n            if (claim.claimed) {\n              preclaimedInteraction = claim;\n              return false;\n            }\n            return true;\n          } catch (error) {\n            log("Unable to preflight Interaction Sessions; bypassing Turn Collector.", {\n              guildId: guildMessage.guildId,\n              channelId: location.channelId,\n              sourceMessageId: guildMessage.id,\n              error: error instanceof Error ? error.message : String(error)\n            });\n            return false;\n          }\n        }\n      : undefined,\n    execute: async (burst) => {\n      await executeQueued(burst, preclaimedInteraction);\n    }\n  });\n}\n'''
    text = prefix + scheduling + suffix

    text = replace_once(
        text,
        '      smart_participation_semantic_enabled: true,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        '      smart_participation_semantic_enabled: true,\n'
        '      smart_participation_turn_collector_enabled: turnIngress.enabled,\n'
        '      smart_participation_turn_collector_pending_scopes:\n'
        '        turnIngress.pendingBurstScopeCount,\n'
        '      smart_participation_ingress_pending_scopes:\n'
        '        turnIngress.pendingPreflightScopeCount,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        "index health collector fields",
    )
    text = replace_once(
        text,
        '  recoveryLoop?.stop();\n'
        '  await eventReporter.stop();\n'
        '  if (heartbeatTimer) clearInterval(heartbeatTimer);\n',
        '  recoveryLoop?.stop();\n'
        '  client.removeAllListeners(Events.MessageCreate);\n'
        '  await turnIngress.shutdown(true);\n'
        '  await Promise.all([...queues.values()].map((task) => task.catch(() => undefined)));\n'
        '  await eventReporter.stop();\n'
        '  if (heartbeatTimer) clearInterval(heartbeatTimer);\n',
        "index shutdown collector drain",
    )

    INDEX.write_text(text, encoding="utf-8")


def patch_relay_client() -> None:
    text = RELAY.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'export interface DiscordSemanticParticipationResult {\n'
        '  available: boolean;\n'
        '  reason: string;\n'
        '  model: string;\n'
        '  dimension: number;\n'
        '  candidates: DiscordSemanticParticipationCandidate[];\n'
        '}\n\n',
        'export interface DiscordSemanticParticipationResult {\n'
        '  available: boolean;\n'
        '  reason: string;\n'
        '  model: string;\n'
        '  dimension: number;\n'
        '  candidates: DiscordSemanticParticipationCandidate[];\n'
        '}\n\n'
        'export interface DiscordParticipationBurstMessage {\n'
        '  message_id: string;\n'
        '  author_id: string;\n'
        '  author_display_name: string;\n'
        '  text: string;\n'
        '  created_at: string;\n'
        '  reply_to_message_id: string;\n'
        '}\n\n'
        'export interface DiscordSmartParticipationScoreRequest {\n'
        '  message: string;\n'
        '  deployment_ids: string[];\n'
        '  guild_id?: string;\n'
        '  channel_id?: string;\n'
        '  thread_id?: string;\n'
        '  message_id?: string;\n'
        '  author_id?: string;\n'
        '  reply_to_message_id?: string;\n'
        '  burst_id?: string;\n'
        '  burst_messages?: DiscordParticipationBurstMessage[];\n'
        '}\n\n',
        "relay burst request interfaces",
    )

    method_pattern = r'''  async scoreSmartParticipation\(payload: \{\n    message: string;\n    deployment_ids: string\[\];\n  \}\): Promise<DiscordSemanticParticipationResult> \{.*?(?=  async claimSocialTurnOperation\()'''
    method = '''  async scoreSmartParticipation(\n    payload: DiscordSmartParticipationScoreRequest\n  ): Promise<DiscordSemanticParticipationResult> {\n    const cachedCandidates = payload.deployment_ids.flatMap((deploymentId) => {\n      const deployment = this.deploymentCache.get(deploymentId);\n      return deployment ? [deployment] : [];\n    });\n    const hasBurstContext = Boolean(payload.burst_id || payload.burst_messages?.length);\n    if (!hasBurstContext && cachedCandidates.length === payload.deployment_ids.length) {\n      const explicit = resolveExplicitAudiencePreflight(\n        cachedCandidates,\n        payload.message,\n        null,\n        configuredGroupAliases()\n      );\n      if (explicit) {\n        return {\n          available: false,\n          reason: `explicit_audience_preflight:${explicit.reason}`,\n          model: "",\n          dimension: 0,\n          candidates: []\n        };\n      }\n    }\n\n    const hardPreflight =\n      cachedCandidates.length === payload.deployment_ids.length\n        ? preflightSmartParticipationCandidates(cachedCandidates, payload.message)\n        : [];\n    const hardPreflightById = new Map(\n      hardPreflight.map((candidate) => [candidate.deploymentId, candidate])\n    );\n    if (hardPreflight.length && hardPreflight.every((candidate) => !candidate.eligible)) {\n      return {\n        available: false,\n        reason: "hard_preflight_no_eligible_candidates",\n        model: "",\n        dimension: 0,\n        candidates: []\n      };\n    }\n\n    try {\n      const resolved = await this.request<DiscordV4ParticipationResult>(\n        "/api/smart-participation/resolve",\n        {\n          method: "POST",\n          body: JSON.stringify({\n            connection_id: this.connectionId,\n            guild_id: payload.guild_id ?? "",\n            channel_id: payload.channel_id ?? "",\n            thread_id: payload.thread_id ?? "",\n            message_id: payload.message_id ?? "",\n            author_id: payload.author_id ?? "",\n            reply_to_message_id: payload.reply_to_message_id ?? "",\n            message: payload.message,\n            burst_id: payload.burst_id ?? "",\n            burst_messages: payload.burst_messages ?? [],\n            candidates: payload.deployment_ids.map((deploymentId) => {\n              const preflight = hardPreflightById.get(deploymentId);\n              return {\n                deployment_id: deploymentId,\n                eligible: preflight?.eligible ?? true,\n                deterministic_score: 0,\n                minimum_score: preflight?.minimumScore ?? 0,\n                signals: preflight?.signals ?? {}\n              };\n            })\n          })\n        }\n      );\n      return {\n        available: resolved.available,\n        reason: `v4_resolver:${resolved.reason}`,\n        model: resolved.model,\n        dimension: resolved.dimension,\n        candidates: resolved.candidates.map((candidate) => ({\n          deployment_id: candidate.deployment_id,\n          character_card_id: candidate.character_card_id,\n          semantic_relevance: candidate.raw_e5_relevance,\n          profile_ready: candidate.profile_ready\n        }))\n      };\n    } catch (error) {\n      if (!missingV4Resolver(error)) throw error;\n    }\n\n    return this.request<DiscordSemanticParticipationResult>(\n      "/api/smart-participation/semantic-score",\n      {\n        method: "POST",\n        body: JSON.stringify({\n          connection_id: this.connectionId,\n          message: payload.message,\n          deployment_ids: payload.deployment_ids\n        })\n      }\n    );\n  }\n\n'''
    text = replace_regex_once(text, method_pattern, method, "relay score method")
    RELAY.write_text(text, encoding="utf-8")


def write_burst_test() -> None:
    BURST_TEST.write_text(
        '''import { afterEach, describe, expect, it, vi } from "vitest";\n\nimport { RelayClient } from "./relayClient.js";\nimport type { DiscordDeployment } from "./types.js";\n\nfunction deployment(name: string): DiscordDeployment {\n  return {\n    deployment_id: `deployment-${name}`,\n    connection_id: "connection-1",\n    character_card_id: `character-${name}`,\n    character_display_name: name,\n    workspace_id: "guild-1",\n    workspace_name: "Guild",\n    channel_id: "channel-1",\n    channel_name: "general",\n    thread_id: "",\n    thread_name: "",\n    category_id: "category-1",\n    server_profile_id: "",\n    channel_scope_mode: "exact",\n    excluded_channel_ids: [],\n    excluded_category_ids: [],\n    participation_mode: "smart",\n    version_label: "Current",\n    status: "active",\n    identity_mode: "webhook",\n    identity_display_name: name,\n    identity_avatar_url: "",\n    address_aliases: [name],\n    webhook_status: "pending",\n    webhook_id: null,\n    webhook_token: null,\n    orchestration_mode: "off"\n  };\n}\n\nfunction jsonResponse(value: unknown, status = 200): Response {\n  return new Response(JSON.stringify(value), {\n    status,\n    headers: { "Content-Type": "application/json" }\n  });\n}\n\ndescribe("RelayClient V4 burst provenance", () => {\n  afterEach(() => {\n    vi.unstubAllGlobals();\n  });\n\n  it("forwards scope and ordered burst messages to the V4 resolver", async () => {\n    const ann = deployment("Ann");\n    let resolverBody: Record<string, unknown> | null = null;\n    vi.stubGlobal(\n      "fetch",\n      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {\n        const url = new URL(\n          typeof input === "string" ? input : input instanceof URL ? input.href : input.url\n        );\n        if (url.pathname === "/api/connectors/discord/deployments") {\n          return jsonResponse([ann]);\n        }\n        if (url.pathname === "/api/smart-participation/connector-profiles") {\n          return jsonResponse({});\n        }\n        if (url.pathname === "/api/smart-participation/resolve") {\n          resolverBody = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;\n          return jsonResponse({\n            resolver_version: "conversation-intelligence-v4-shadow-1",\n            available: true,\n            reason: "ok",\n            model: "e5",\n            dimension: 1024,\n            burst_id: "burst-123",\n            burst_message_count: 2,\n            analysis_chars: 20,\n            candidates: [],\n            speaker_plan: [],\n            graph_shadow_observed: true,\n            graph_shadow_node_count: 3,\n            graph_shadow_edge_count: 2,\n            graph_used: false,\n            learned_state_used: false,\n            utility_used: false\n          });\n        }\n        throw new Error(`unexpected request ${url.pathname}`);\n      })\n    );\n\n    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");\n    await relay.listDeployments();\n    await relay.scoreSmartParticipation({\n      message: "first\\nsecond",\n      deployment_ids: [ann.deployment_id],\n      guild_id: "guild-1",\n      channel_id: "channel-1",\n      thread_id: "thread-1",\n      message_id: "message-2",\n      author_id: "user-2",\n      burst_id: "burst-123",\n      burst_messages: [\n        {\n          message_id: "message-1",\n          author_id: "user-1",\n          author_display_name: "Alice",\n          text: "first",\n          created_at: "2026-08-14T12:00:00Z",\n          reply_to_message_id: ""\n        },\n        {\n          message_id: "message-2",\n          author_id: "user-2",\n          author_display_name: "Bob",\n          text: "second",\n          created_at: "2026-08-14T12:00:01Z",\n          reply_to_message_id: ""\n        }\n      ]\n    });\n\n    expect(resolverBody).toMatchObject({\n      connection_id: "connection-1",\n      guild_id: "guild-1",\n      channel_id: "channel-1",\n      thread_id: "thread-1",\n      message_id: "message-2",\n      author_id: "user-2",\n      burst_id: "burst-123"\n    });\n    expect(resolverBody?.burst_messages).toEqual([\n      {\n        message_id: "message-1",\n        author_id: "user-1",\n        author_display_name: "Alice",\n        text: "first",\n        created_at: "2026-08-14T12:00:00Z",\n        reply_to_message_id: ""\n      },\n      {\n        message_id: "message-2",\n        author_id: "user-2",\n        author_display_name: "Bob",\n        text: "second",\n        created_at: "2026-08-14T12:00:01Z",\n        reply_to_message_id: ""\n      }\n    ]);\n  });\n\n  it("keeps the legacy fallback payload narrow", async () => {\n    const ann = deployment("Ann");\n    let legacyBody: Record<string, unknown> | null = null;\n    vi.stubGlobal(\n      "fetch",\n      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {\n        const url = new URL(\n          typeof input === "string" ? input : input instanceof URL ? input.href : input.url\n        );\n        if (url.pathname === "/api/connectors/discord/deployments") return jsonResponse([ann]);\n        if (url.pathname === "/api/smart-participation/connector-profiles") return jsonResponse({});\n        if (url.pathname === "/api/smart-participation/resolve") {\n          return jsonResponse({ detail: "Not Found" }, 404);\n        }\n        if (url.pathname === "/api/smart-participation/semantic-score") {\n          legacyBody = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;\n          return jsonResponse({\n            available: false,\n            reason: "legacy",\n            model: "",\n            dimension: 0,\n            candidates: []\n          });\n        }\n        throw new Error(`unexpected request ${url.pathname}`);\n      })\n    );\n\n    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");\n    await relay.listDeployments();\n    await relay.scoreSmartParticipation({\n      message: "ordinary",\n      deployment_ids: [ann.deployment_id],\n      guild_id: "guild-1",\n      channel_id: "channel-1",\n      burst_id: "burst-123"\n    });\n\n    expect(legacyBody).toEqual({\n      connection_id: "connection-1",\n      message: "ordinary",\n      deployment_ids: [ann.deployment_id]\n    });\n  });\n});\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_index()
    patch_relay_client()
    write_burst_test()
