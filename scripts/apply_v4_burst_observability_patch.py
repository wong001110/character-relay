from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "connectors/discord/src/index.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = INDEX.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '  buildConversationBurstText,\n'
        '  decideTurnCollection\n'
        '} from "./turnIngress.js";\n',
        '  buildConversationBurstText,\n'
        '  decideTurnCollection,\n'
        '  summarizeConversationBurst\n'
        '} from "./turnIngress.js";\n',
        "turn ingress telemetry import",
    )

    text = replace_once(
        text,
        'let lastGatewayMentionedBot = false;\n'
        'const turnIngress = new TurnIngressCoordinator<CollectedDiscordTurn>(\n',
        'let lastGatewayMentionedBot = false;\n'
        'let turnCollectorCandidateMessageCount = 0;\n'
        'let turnCollectorBypassMessageCount = 0;\n'
        'let turnCollectorBurstCount = 0;\n'
        'let turnCollectorCollectedMessageCount = 0;\n'
        'let turnCollectorCollapsedMessageCount = 0;\n'
        'let turnCollectorInteractionBypassCount = 0;\n'
        'let turnCollectorLastBurstAt: string | null = null;\n'
        'let turnCollectorLastBurstId: string | null = null;\n'
        'let turnCollectorLastFlushReason: string | null = null;\n'
        'const turnCollectorBypassReasons: Record<string, number> = {};\n'
        'const turnIngress = new TurnIngressCoordinator<CollectedDiscordTurn>(\n',
        "turn collector counters",
    )

    text = replace_once(
        text,
        '  ): Promise<void> => {\n'
        '    if (burst) {\n',
        '  ): Promise<void> => {\n'
        '    const burstTelemetry = burst\n'
        '      ? summarizeConversationBurst(\n'
        '          burst,\n'
        '          burst.items.map((item) => item.source.author.id)\n'
        '        )\n'
        '      : null;\n'
        '    if (burstTelemetry) {\n'
        '      turnCollectorBurstCount += 1;\n'
        '      turnCollectorCollectedMessageCount += burstTelemetry.messageCount;\n'
        '      turnCollectorCollapsedMessageCount += burstTelemetry.collapsedMessageCount;\n'
        '      turnCollectorLastBurstAt = new Date(burstTelemetry.flushedAt).toISOString();\n'
        '      turnCollectorLastBurstId = burstTelemetry.burstId;\n'
        '      turnCollectorLastFlushReason = burstTelemetry.flushReason;\n'
        '      reportDiscordEvent({\n'
        '        level: "info",\n'
        '        eventType: "smart_participation_burst_flushed",\n'
        '        message: "Turn Collector flushed a bounded Conversation Burst for Smart Participation.",\n'
        '        guildId: guildMessage.guildId,\n'
        '        guildName: guildMessage.guild.name,\n'
        '        channelId: location.channelId,\n'
        '        channelName: location.channelName,\n'
        '        threadId: location.threadId,\n'
        '        threadName: location.threadName,\n'
        '        sourceMessageId: guildMessage.id,\n'
        '        details: {\n'
        '          burst_id: burstTelemetry.burstId,\n'
        '          flush_reason: burstTelemetry.flushReason,\n'
        '          message_count: burstTelemetry.messageCount,\n'
        '          author_count: burstTelemetry.authorCount,\n'
        '          total_characters: burstTelemetry.totalCharacters,\n'
        '          opened_at: new Date(burstTelemetry.openedAt).toISOString(),\n'
        '          flushed_at: new Date(burstTelemetry.flushedAt).toISOString(),\n'
        '          collection_latency_ms: burstTelemetry.collectionLatencyMs,\n'
        '          collapsed_message_count: burstTelemetry.collapsedMessageCount,\n'
        '          source_message_ids: burstTelemetry.sourceMessageIds\n'
        '        }\n'
        '      });\n'
        '    }\n'
        '    if (burst) {\n',
        "burst telemetry execution",
    )

    text = replace_once(
        text,
        '    const participationBurstId = burst ? buildConversationBurstId(burst.itemIds) : "";\n',
        '    const participationBurstId = burstTelemetry?.burstId ?? "";\n',
        "reuse burst telemetry id",
    )

    text = replace_once(
        text,
        '              candidate_count: semantic.candidates.length,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        '              candidate_count: semantic.candidates.length,\n'
        '              burst_id: burstTelemetry?.burstId ?? null,\n'
        '              burst_message_count: burstTelemetry?.messageCount ?? 1,\n'
        '              collapsed_message_count: burstTelemetry?.collapsedMessageCount ?? 0,\n'
        '              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        "semantic event burst correlation",
    )

    text = replace_once(
        text,
        '            details: {\n'
        '              error: error instanceof Error ? error.message : String(error),\n'
        '              candidate_count: smartDeploymentIds.length\n'
        '            }\n'
        '          });\n',
        '            details: {\n'
        '              error: error instanceof Error ? error.message : String(error),\n'
        '              candidate_count: smartDeploymentIds.length,\n'
        '              burst_id: burstTelemetry?.burstId ?? null,\n'
        '              burst_message_count: burstTelemetry?.messageCount ?? 1,\n'
        '              turn_collector_flush_reason: burstTelemetry?.flushReason ?? null\n'
        '            }\n'
        '          });\n',
        "semantic failure burst correlation",
    )

    text = replace_once(
        text,
        '  if (collectionDecision.collect) {\n'
        '    log("Smart Participation message entered the Turn Collector.", {\n',
        '  if (collectionDecision.collect) {\n'
        '    turnCollectorCandidateMessageCount += 1;\n'
        '    log("Smart Participation message entered the Turn Collector.", {\n',
        "candidate message counter",
    )

    text = replace_once(
        text,
        '      quietWindowMs: config.smartParticipationTurnCollectorQuietMs\n'
        '    });\n'
        '  }\n\n'
        '  turnIngress.submit(key, {\n',
        '      quietWindowMs: config.smartParticipationTurnCollectorQuietMs\n'
        '    });\n'
        '  } else {\n'
        '    turnCollectorBypassMessageCount += 1;\n'
        '    turnCollectorBypassReasons[collectionDecision.reason] =\n'
        '      (turnCollectorBypassReasons[collectionDecision.reason] ?? 0) + 1;\n'
        '  }\n\n'
        '  turnIngress.submit(key, {\n',
        "bypass counters",
    )

    text = replace_once(
        text,
        '            if (claim.claimed) {\n'
        '              preclaimedInteraction = claim;\n'
        '              return false;\n'
        '            }\n',
        '            if (claim.claimed) {\n'
        '              turnCollectorInteractionBypassCount += 1;\n'
        '              preclaimedInteraction = claim;\n'
        '              return false;\n'
        '            }\n',
        "interaction claimed bypass counter",
    )

    text = replace_once(
        text,
        '          } catch (error) {\n'
        '            log("Unable to preflight Interaction Sessions; bypassing Turn Collector.", {\n',
        '          } catch (error) {\n'
        '            turnCollectorInteractionBypassCount += 1;\n'
        '            log("Unable to preflight Interaction Sessions; bypassing Turn Collector.", {\n',
        "interaction error bypass counter",
    )

    text = replace_once(
        text,
        '      smart_participation_ingress_pending_scopes:\n'
        '        turnIngress.pendingPreflightScopeCount,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        '      smart_participation_ingress_pending_scopes:\n'
        '        turnIngress.pendingPreflightScopeCount,\n'
        '      smart_participation_turn_collector_candidate_messages:\n'
        '        turnCollectorCandidateMessageCount,\n'
        '      smart_participation_turn_collector_bypass_messages:\n'
        '        turnCollectorBypassMessageCount,\n'
        '      smart_participation_turn_collector_bypass_reasons:\n'
        '        turnCollectorBypassReasons,\n'
        '      smart_participation_turn_collector_interaction_bypasses:\n'
        '        turnCollectorInteractionBypassCount,\n'
        '      smart_participation_turn_collector_bursts: turnCollectorBurstCount,\n'
        '      smart_participation_turn_collector_collected_messages:\n'
        '        turnCollectorCollectedMessageCount,\n'
        '      smart_participation_turn_collector_collapsed_messages:\n'
        '        turnCollectorCollapsedMessageCount,\n'
        '      smart_participation_turn_collector_last_burst_at: turnCollectorLastBurstAt,\n'
        '      smart_participation_turn_collector_last_burst_id: turnCollectorLastBurstId,\n'
        '      smart_participation_turn_collector_last_flush_reason:\n'
        '        turnCollectorLastFlushReason,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        "health burst counters",
    )

    INDEX.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
