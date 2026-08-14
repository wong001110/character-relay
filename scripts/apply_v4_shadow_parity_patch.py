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
        'import { DiscordEventReporter } from "./eventReporter.js";\n'
        'import { RelayClient } from "./relayClient.js";\n',
        'import { DiscordEventReporter } from "./eventReporter.js";\n'
        'import { compareParticipationShadowPlan } from "./participationShadowParity.js";\n'
        'import {\n'
        '  RelayClient,\n'
        '  type DiscordParticipationShadowCandidate,\n'
        '  type DiscordParticipationShadowPlanItem\n'
        '} from "./relayClient.js";\n',
        "parity imports",
    )

    text = replace_once(
        text,
        'let turnCollectorLastFlushReason: string | null = null;\n'
        'const turnCollectorBypassReasons: Record<string, number> = {};\n',
        'let turnCollectorLastFlushReason: string | null = null;\n'
        'let participationShadowParityObservationCount = 0;\n'
        'let participationShadowParityExactMatchCount = 0;\n'
        'let participationShadowParitySetMatchCount = 0;\n'
        'let participationShadowParityMismatchCount = 0;\n'
        'let participationShadowParityLastAt: string | null = null;\n'
        'let participationShadowParityLastExactMatch: boolean | null = null;\n'
        'let participationShadowParityLastSetMatch: boolean | null = null;\n'
        'const turnCollectorBypassReasons: Record<string, number> = {};\n',
        "parity counters",
    )

    text = replace_once(
        text,
        '    const semanticScores: Record<string, number> = {};\n'
        '    const smartRuntimeScopeKey = [\n',
        '    const semanticScores: Record<string, number> = {};\n'
        '    let serverShadowPlan: DiscordParticipationShadowPlanItem[] | undefined;\n'
        '    let serverShadowCandidateScores:\n'
        '      | DiscordParticipationShadowCandidate[]\n'
        '      | undefined;\n'
        '    const smartRuntimeScopeKey = [\n',
        "shadow local state",
    )

    text = replace_once(
        text,
        '          if (semantic.available) {\n'
        '            for (const candidate of semantic.candidates) {\n',
        '          serverShadowPlan = semantic.shadow_speaker_plan;\n'
        '          serverShadowCandidateScores = semantic.shadow_candidate_scores;\n'
        '          if (semantic.available) {\n'
        '            for (const candidate of semantic.candidates) {\n',
        "capture shadow response",
    )

    text = replace_once(
        text,
        '    const audience = resolveAudience(\n'
        '      candidates,\n'
        '      participationText,\n'
        '      replyTarget.deploymentId,\n'
        '      config.groupAddressAliases,\n'
        '      semanticScores,\n'
        '      smartRuntimeScopeKey\n'
        '    );\n'
        '    if (!audience.deployments.length) {\n',
        '    const audience = resolveAudience(\n'
        '      candidates,\n'
        '      participationText,\n'
        '      replyTarget.deploymentId,\n'
        '      config.groupAddressAliases,\n'
        '      semanticScores,\n'
        '      smartRuntimeScopeKey\n'
        '    );\n'
        '    const actualSmartDeploymentIds =\n'
        '      audience.reason === "selected_smart" || audience.reason === "selected_smart_multiple"\n'
        '        ? audience.deployments.map((deployment) => deployment.deployment_id)\n'
        '        : [];\n'
        '    const shadowParity = compareParticipationShadowPlan(\n'
        '      serverShadowPlan,\n'
        '      actualSmartDeploymentIds,\n'
        '      serverShadowCandidateScores\n'
        '    );\n'
        '    if (shadowParity.observed) {\n'
        '      participationShadowParityObservationCount += 1;\n'
        '      if (shadowParity.exactMatch) participationShadowParityExactMatchCount += 1;\n'
        '      if (shadowParity.setMatch) participationShadowParitySetMatchCount += 1;\n'
        '      if (!shadowParity.setMatch) participationShadowParityMismatchCount += 1;\n'
        '      participationShadowParityLastAt = new Date().toISOString();\n'
        '      participationShadowParityLastExactMatch = shadowParity.exactMatch;\n'
        '      participationShadowParityLastSetMatch = shadowParity.setMatch;\n'
        '      reportDiscordEvent({\n'
        '        level: shadowParity.setMatch ? "info" : "warning",\n'
        '        eventType: "smart_participation_shadow_parity",\n'
        '        message: shadowParity.setMatch\n'
        '          ? "Server shadow speaker plan matched the authoritative Connector speaker set."\n'
        '          : "Server shadow speaker plan disagreed with the authoritative Connector speaker set.",\n'
        '        guildId: guildMessage.guildId,\n'
        '        guildName: guildMessage.guild.name,\n'
        '        channelId: location.channelId,\n'
        '        channelName: location.channelName,\n'
        '        threadId: location.threadId,\n'
        '        threadName: location.threadName,\n'
        '        sourceMessageId: guildMessage.id,\n'
        '        details: {\n'
        '          burst_id: burstTelemetry?.burstId ?? null,\n'
        '          audience_reason: audience.reason,\n'
        '          exact_match: shadowParity.exactMatch,\n'
        '          set_match: shadowParity.setMatch,\n'
        '          shadow_deployment_ids: shadowParity.shadowDeploymentIds,\n'
        '          actual_deployment_ids: shadowParity.actualDeploymentIds,\n'
        '          missing_from_shadow: shadowParity.missingFromShadow,\n'
        '          extra_in_shadow: shadowParity.extraInShadow,\n'
        '          shadow_candidate_scores: shadowParity.shadowCandidateScores\n'
        '        }\n'
        '      });\n'
        '    }\n'
        '    if (!audience.deployments.length) {\n',
        "emit shadow parity",
    )

    text = replace_once(
        text,
        '      smart_participation_turn_collector_last_flush_reason:\n'
        '        turnCollectorLastFlushReason,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        '      smart_participation_turn_collector_last_flush_reason:\n'
        '        turnCollectorLastFlushReason,\n'
        '      smart_participation_shadow_parity_observations:\n'
        '        participationShadowParityObservationCount,\n'
        '      smart_participation_shadow_parity_exact_matches:\n'
        '        participationShadowParityExactMatchCount,\n'
        '      smart_participation_shadow_parity_set_matches:\n'
        '        participationShadowParitySetMatchCount,\n'
        '      smart_participation_shadow_parity_mismatches:\n'
        '        participationShadowParityMismatchCount,\n'
        '      smart_participation_shadow_parity_last_at:\n'
        '        participationShadowParityLastAt,\n'
        '      smart_participation_shadow_parity_last_exact_match:\n'
        '        participationShadowParityLastExactMatch,\n'
        '      smart_participation_shadow_parity_last_set_match:\n'
        '        participationShadowParityLastSetMatch,\n'
        '      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n',
        "health parity counters",
    )

    INDEX.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
