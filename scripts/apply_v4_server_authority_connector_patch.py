from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELAY = ROOT / "connectors/discord/src/relayClient.ts"
INDEX = ROOT / "connectors/discord/src/index.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def patch_relay() -> None:
    text = RELAY.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "  candidates: DiscordSemanticParticipationCandidate[];\n"
        "  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n",
        "  candidates: DiscordSemanticParticipationCandidate[];\n"
        "  speaker_plan?: DiscordParticipationShadowPlanItem[];\n"
        "  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n",
        "public speaker plan type",
    )
    text = replace_once(
        text,
        "  minimum_margin?: number;\n"
        "  max_participants?: number;\n"
        "  candidate_preflight?: DiscordSmartParticipationCandidatePreflight[];\n",
        "  minimum_margin?: number;\n"
        "  max_participants?: number;\n"
        "  channel_cooldown_seconds?: number;\n"
        "  window_seconds?: number;\n"
        "  max_replies_per_window?: number;\n"
        "  candidate_preflight?: DiscordSmartParticipationCandidatePreflight[];\n",
        "durable request policy type",
    )
    text = replace_once(
        text,
        "  candidates: DiscordV4ParticipationCandidate[];\n"
        "  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n",
        "  candidates: DiscordV4ParticipationCandidate[];\n"
        "  speaker_plan?: DiscordParticipationShadowPlanItem[];\n"
        "  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n",
        "v4 speaker plan type",
    )
    text = replace_once(
        text,
        "            minimum_margin: payload.minimum_margin ?? 2,\n"
        "            max_participants: payload.max_participants ?? 2,\n"
        "            candidates: payload.deployment_ids.map((deploymentId) => {\n",
        "            minimum_margin: payload.minimum_margin ?? 2,\n"
        "            max_participants: payload.max_participants ?? 2,\n"
        "            channel_cooldown_seconds: payload.channel_cooldown_seconds ?? 45,\n"
        "            window_seconds: payload.window_seconds ?? 600,\n"
        "            max_replies_per_window: payload.max_replies_per_window ?? 3,\n"
        "            candidates: payload.deployment_ids.map((deploymentId) => {\n",
        "durable request policy body",
    )
    text = replace_once(
        text,
        "        dimension: resolved.dimension,\n"
        "        shadow_speaker_plan: resolved.shadow_speaker_plan ?? [],\n",
        "        dimension: resolved.dimension,\n"
        "        speaker_plan: resolved.speaker_plan ?? [],\n"
        "        shadow_speaker_plan: resolved.shadow_speaker_plan ?? [],\n",
        "relay result speaker plan",
    )
    marker = "\n  async claimSocialTurnOperation(\n"
    method = '''\n  async observeSmartParticipationOutcome(input: {\n    guild_id: string;\n    channel_id: string;\n    thread_id: string;\n    message_id: string;\n    burst_id: string;\n    author_id: string;\n    reply_to_message_id: string;\n    selected_deployment_ids: string[];\n    candidate_deployment_ids: string[];\n  }): Promise<void> {\n    await this.request<void>(\"/api/smart-participation/observe\", {\n      method: \"POST\",\n      body: JSON.stringify({ connection_id: this.connectionId, ...input })\n    });\n  }\n'''
    if "async observeSmartParticipationOutcome" not in text:
        text = replace_once(text, marker, method + marker, "outcome client method")
    RELAY.write_text(text, encoding="utf-8")


def patch_index() -> None:
    text = INDEX.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    let serverShadowPlan: DiscordParticipationShadowPlanItem[] | undefined;\n"
        "    let serverShadowCandidateScores:\n"
        "      | DiscordParticipationShadowCandidate[]\n"
        "      | undefined;\n",
        "    let serverSpeakerPlan: DiscordParticipationShadowPlanItem[] | undefined;\n"
        "    let serverSpeakerPlanAuthoritative = false;\n"
        "    let serverShadowPlan: DiscordParticipationShadowPlanItem[] | undefined;\n"
        "    let serverShadowCandidateScores:\n"
        "      | DiscordParticipationShadowCandidate[]\n"
        "      | undefined;\n",
        "server speaker variables",
    )
    text = replace_once(
        text,
        "            minimum_margin: config.smartParticipationMinimumMargin,\n"
        "            max_participants: config.smartParticipationMaxParticipants,\n"
        "            candidate_preflight: smartDeploymentIds.map((deploymentId) => {\n",
        "            minimum_margin: config.smartParticipationMinimumMargin,\n"
        "            max_participants: config.smartParticipationMaxParticipants,\n"
        "            channel_cooldown_seconds: config.smartParticipationChannelCooldownSeconds,\n"
        "            window_seconds: config.smartParticipationWindowSeconds,\n"
        "            max_replies_per_window: config.smartParticipationMaxRepliesPerWindow,\n"
        "            candidate_preflight: smartDeploymentIds.map((deploymentId) => {\n",
        "send durable policy",
    )
    text = replace_once(
        text,
        "          serverShadowPlan = semantic.shadow_speaker_plan;\n"
        "          serverShadowCandidateScores = semantic.shadow_candidate_scores;\n",
        "          serverSpeakerPlan = semantic.speaker_plan;\n"
        "          serverSpeakerPlanAuthoritative = Boolean(semantic.speaker_plan_authoritative);\n"
        "          serverShadowPlan = semantic.shadow_speaker_plan;\n"
        "          serverShadowCandidateScores = semantic.shadow_candidate_scores;\n",
        "capture server speaker plan",
    )
    text = replace_once(
        text,
        "              semantic_preflight_reason: semanticPreflight.reason,\n"
        "              shadow_speaker_plan: semantic.shadow_speaker_plan ?? [],\n",
        "              semantic_preflight_reason: semanticPreflight.reason,\n"
        "              speaker_plan: semantic.speaker_plan ?? [],\n"
        "              shadow_speaker_plan: semantic.shadow_speaker_plan ?? [],\n",
        "event speaker plan",
    )
    old = '''    const audience = resolveAudience(\n      candidates,\n      participationText,\n      replyTarget.deploymentId,\n      config.groupAddressAliases,\n      semanticScores,\n      smartRuntimeScopeKey\n    );\n'''
    new = '''    let audience = resolveAudience(\n      candidates,\n      participationText,\n      replyTarget.deploymentId,\n      config.groupAddressAliases,\n      semanticScores,\n      smartRuntimeScopeKey\n    );\n    if (serverSpeakerPlanAuthoritative && !replyTarget.deploymentId) {\n      const planned = (serverSpeakerPlan ?? [])\n        .map((item) =>\n          candidates.find((candidate) => candidate.deployment_id === item.deployment_id)\n        )\n        .filter((item): item is DiscordDeployment => Boolean(item));\n      audience = {\n        deployments: planned,\n        text: participationText.trim(),\n        reason:\n          planned.length > 1\n            ? \"selected_smart_multiple\"\n            : planned.length === 1\n              ? \"selected_smart\"\n              : \"not_found\",\n        options: []\n      };\n    }\n'''
    text = replace_once(text, old, new, "authoritative audience")
    marker = '''    const shadowParity = compareParticipationShadowPlan(\n'''
    observe = '''    if (actualSmartDeploymentIds.length) {\n      void relay\n        .observeSmartParticipationOutcome({\n          guild_id: guildMessage.guildId,\n          channel_id: location.channelId,\n          thread_id: location.threadId,\n          message_id: guildMessage.id,\n          burst_id: participationBurstId,\n          author_id: guildMessage.author.id,\n          reply_to_message_id: guildMessage.reference?.messageId ?? \"\",\n          selected_deployment_ids: actualSmartDeploymentIds,\n          candidate_deployment_ids: candidates\n            .filter((candidate) => candidate.participation_mode === \"smart\")\n            .map((candidate) => candidate.deployment_id)\n        })\n        .catch((error) => {\n          reportDiscordEvent({\n            level: \"warning\",\n            eventType: \"smart_participation_outcome_failed\",\n            message: \"Server could not persist Smart Participation outcome state.\",\n            guildId: guildMessage.guildId,\n            guildName: guildMessage.guild.name,\n            channelId: location.channelId,\n            channelName: location.channelName,\n            threadId: location.threadId,\n            threadName: location.threadName,\n            sourceMessageId: guildMessage.id,\n            details: {\n              error: error instanceof Error ? error.message : String(error),\n              selected_deployment_ids: actualSmartDeploymentIds\n            }\n          });\n        });\n    }\n'''
    if "observeSmartParticipationOutcome" not in text:
        text = replace_once(text, marker, observe + marker, "outcome observation")
    INDEX.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_relay()
    patch_index()
