from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMART = ROOT / "connectors/discord/src/smartParticipation.ts"
INDEX = ROOT / "connectors/discord/src/index.ts"
RELAY = ROOT / "connectors/discord/src/relayClient.ts"
TEST = ROOT / "connectors/discord/src/participationShadowBridge.test.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_smart() -> None:
    text = SMART.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'export interface SmartParticipationSemanticPreflight {\n'
        '  skipSemantic: boolean;\n'
        '  reason: SmartParticipationSemanticPreflightReason;\n'
        '  semanticCandidateDeploymentIds: string[];\n'
        '}\n\n',
        'export interface SmartParticipationSemanticPreflight {\n'
        '  skipSemantic: boolean;\n'
        '  reason: SmartParticipationSemanticPreflightReason;\n'
        '  semanticCandidateDeploymentIds: string[];\n'
        '}\n\n'
        'export interface SmartParticipationBaseEvidence {\n'
        '  deploymentId: string;\n'
        '  eligible: boolean;\n'
        '  deterministicScore: number;\n'
        '  minimumScore: number;\n'
        '  signals: SmartParticipationSignals;\n'
        '}\n\n',
        "base evidence interface",
    )

    marker = 'export function preflightSmartParticipationRuntime(\n'
    if text.count(marker) != 1:
        raise RuntimeError("preflight marker changed")
    helper = '''export function buildSmartParticipationBaseEvidence(
  deployments: DiscordDeployment[],
  message: string,
  now = Date.now()
): SmartParticipationBaseEvidence[] {
  const text = normalizeText(message);
  if (!text) return [];
  pruneSelections(now);
  return deployments
    .filter((deployment) => deployment.participation_mode === "smart")
    .map((deployment) => scoreCandidate(deployment, text, now, undefined))
    .map((candidate) => ({
      deploymentId: candidate.deployment.deployment_id,
      eligible: candidate.eligible,
      deterministicScore: Number.isFinite(candidate.score) ? candidate.score : -100,
      minimumScore: candidate.minimumScore,
      signals: { ...candidate.signals }
    }));
}

'''
    text = text.replace(marker, helper + marker, 1)
    SMART.write_text(text, encoding="utf-8")


def patch_index() -> None:
    text = INDEX.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'import { preflightSmartParticipationRuntime } from "./smartParticipation.js";\n',
        'import {\n'
        '  buildSmartParticipationBaseEvidence,\n'
        '  preflightSmartParticipationRuntime\n'
        '} from "./smartParticipation.js";\n',
        "index evidence imports",
    )
    text = replace_once(
        text,
        '      const semanticPreflight = preflightSmartParticipationRuntime(\n'
        '        candidates,\n'
        '        participationText,\n'
        '        Date.now(),\n'
        '        smartRuntimeScopeKey\n'
        '      );\n'
        '      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;\n',
        '      const semanticPreflightNow = Date.now();\n'
        '      const semanticPreflight = preflightSmartParticipationRuntime(\n'
        '        candidates,\n'
        '        participationText,\n'
        '        semanticPreflightNow,\n'
        '        smartRuntimeScopeKey\n'
        '      );\n'
        '      const smartDeploymentIds = semanticPreflight.semanticCandidateDeploymentIds;\n'
        '      const baseEvidenceById = new Map(\n'
        '        buildSmartParticipationBaseEvidence(\n'
        '          candidates,\n'
        '          participationText,\n'
        '          semanticPreflightNow\n'
        '        ).map((item) => [item.deploymentId, item])\n'
        '      );\n',
        "index build base evidence",
    )
    text = replace_once(
        text,
        '            burst_id: participationBurstId,\n'
        '            burst_messages: participationBurstMessages\n'
        '          });\n',
        '            burst_id: participationBurstId,\n'
        '            burst_messages: participationBurstMessages,\n'
        '            minimum_margin: config.smartParticipationMinimumMargin,\n'
        '            max_participants: config.smartParticipationMaxParticipants,\n'
        '            candidate_preflight: smartDeploymentIds.map((deploymentId) => {\n'
        '              const evidence = baseEvidenceById.get(deploymentId);\n'
        '              return {\n'
        '                deployment_id: deploymentId,\n'
        '                eligible: evidence?.eligible ?? true,\n'
        '                deterministic_score: evidence?.deterministicScore ?? 0,\n'
        '                minimum_score: evidence?.minimumScore ?? 0,\n'
        '                signals: evidence?.signals ?? {}\n'
        '              };\n'
        '            })\n'
        '          });\n',
        "index resolver base evidence payload",
    )
    text = replace_once(
        text,
        '              semantic_preflight_reason: semanticPreflight.reason,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        '              semantic_preflight_reason: semanticPreflight.reason,\n'
        '              shadow_speaker_plan: semantic.shadow_speaker_plan ?? [],\n'
        '              shadow_candidate_scores: semantic.shadow_candidate_scores ?? [],\n'
        '              speaker_plan_authoritative: semantic.speaker_plan_authoritative ?? false,\n'
        '              scores: semantic.candidates.map((candidate) => ({\n',
        "index shadow observability",
    )
    INDEX.write_text(text, encoding="utf-8")


def patch_relay() -> None:
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
        'export interface DiscordParticipationShadowPlanItem {\n'
        '  deployment_id: string;\n'
        '  turn_role: string;\n'
        '  reason: string;\n'
        '}\n\n'
        'export interface DiscordParticipationShadowCandidate {\n'
        '  deployment_id: string;\n'
        '  deterministic_score: number;\n'
        '  semantic_points: number;\n'
        '  shadow_final_score: number;\n'
        '  shadow_selected: boolean;\n'
        '}\n\n'
        'export interface DiscordSemanticParticipationResult {\n'
        '  available: boolean;\n'
        '  reason: string;\n'
        '  model: string;\n'
        '  dimension: number;\n'
        '  candidates: DiscordSemanticParticipationCandidate[];\n'
        '  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n'
        '  shadow_candidate_scores?: DiscordParticipationShadowCandidate[];\n'
        '  speaker_plan_authoritative?: boolean;\n'
        '}\n\n',
        "relay shadow result interfaces",
    )
    text = replace_once(
        text,
        'export interface DiscordSmartParticipationScoreRequest {\n'
        '  message: string;\n'
        '  deployment_ids: string[];\n',
        'export interface DiscordSmartParticipationCandidatePreflight {\n'
        '  deployment_id: string;\n'
        '  eligible: boolean;\n'
        '  deterministic_score: number;\n'
        '  minimum_score: number;\n'
        '  signals: Record<string, number>;\n'
        '}\n\n'
        'export interface DiscordSmartParticipationScoreRequest {\n'
        '  message: string;\n'
        '  deployment_ids: string[];\n',
        "relay candidate preflight interface",
    )
    text = replace_once(
        text,
        '  burst_id?: string;\n'
        '  burst_messages?: DiscordParticipationBurstMessage[];\n'
        '}\n\n',
        '  burst_id?: string;\n'
        '  burst_messages?: DiscordParticipationBurstMessage[];\n'
        '  minimum_margin?: number;\n'
        '  max_participants?: number;\n'
        '  candidate_preflight?: DiscordSmartParticipationCandidatePreflight[];\n'
        '}\n\n',
        "relay score request shadow fields",
    )
    text = replace_once(
        text,
        'interface DiscordV4ParticipationCandidate {\n'
        '  deployment_id: string;\n'
        '  character_card_id: string;\n'
        '  raw_e5_relevance: number;\n'
        '  profile_ready: boolean;\n'
        '}\n\n'
        'interface DiscordV4ParticipationResult {\n'
        '  available: boolean;\n'
        '  reason: string;\n'
        '  model: string;\n'
        '  dimension: number;\n'
        '  candidates: DiscordV4ParticipationCandidate[];\n'
        '}\n',
        'interface DiscordV4ParticipationCandidate {\n'
        '  deployment_id: string;\n'
        '  character_card_id: string;\n'
        '  deterministic_score: number;\n'
        '  raw_e5_relevance: number;\n'
        '  profile_ready: boolean;\n'
        '  semantic_points: number;\n'
        '  shadow_final_score: number;\n'
        '  shadow_selected: boolean;\n'
        '}\n\n'
        'interface DiscordV4ParticipationResult {\n'
        '  available: boolean;\n'
        '  reason: string;\n'
        '  model: string;\n'
        '  dimension: number;\n'
        '  candidates: DiscordV4ParticipationCandidate[];\n'
        '  shadow_speaker_plan?: DiscordParticipationShadowPlanItem[];\n'
        '  speaker_plan_authoritative?: boolean;\n'
        '}\n',
        "relay V4 shadow response shape",
    )

    text = replace_once(
        text,
        '    const hardPreflight =\n'
        '      cachedCandidates.length === payload.deployment_ids.length\n'
        '        ? preflightSmartParticipationCandidates(cachedCandidates, payload.message)\n'
        '        : [];\n'
        '    const hardPreflightById = new Map(\n'
        '      hardPreflight.map((candidate) => [candidate.deploymentId, candidate])\n'
        '    );\n'
        '    if (hardPreflight.length && hardPreflight.every((candidate) => !candidate.eligible)) {\n',
        '    const runtimePreflight = payload.candidate_preflight ?? [];\n'
        '    const hardPreflight =\n'
        '      !runtimePreflight.length && cachedCandidates.length === payload.deployment_ids.length\n'
        '        ? preflightSmartParticipationCandidates(cachedCandidates, payload.message)\n'
        '        : [];\n'
        '    const runtimePreflightById = new Map(\n'
        '      runtimePreflight.map((candidate) => [candidate.deployment_id, candidate])\n'
        '    );\n'
        '    const hardPreflightById = new Map(\n'
        '      hardPreflight.map((candidate) => [candidate.deploymentId, candidate])\n'
        '    );\n'
        '    const effectivePreflight = runtimePreflight.length ? runtimePreflight : hardPreflight;\n'
        '    if (effectivePreflight.length && effectivePreflight.every((candidate) => !candidate.eligible)) {\n',
        "relay runtime preflight preference",
    )

    text = replace_once(
        text,
        '            burst_id: payload.burst_id ?? "",\n'
        '            burst_messages: payload.burst_messages ?? [],\n'
        '            candidates: payload.deployment_ids.map((deploymentId) => {\n'
        '              const preflight = hardPreflightById.get(deploymentId);\n'
        '              return {\n'
        '                deployment_id: deploymentId,\n'
        '                eligible: preflight?.eligible ?? true,\n'
        '                deterministic_score: 0,\n'
        '                minimum_score: preflight?.minimumScore ?? 0,\n'
        '                signals: preflight?.signals ?? {}\n'
        '              };\n'
        '            })\n',
        '            burst_id: payload.burst_id ?? "",\n'
        '            burst_messages: payload.burst_messages ?? [],\n'
        '            minimum_margin: payload.minimum_margin ?? 2,\n'
        '            max_participants: payload.max_participants ?? 2,\n'
        '            candidates: payload.deployment_ids.map((deploymentId) => {\n'
        '              const runtime = runtimePreflightById.get(deploymentId);\n'
        '              const hard = hardPreflightById.get(deploymentId);\n'
        '              return {\n'
        '                deployment_id: deploymentId,\n'
        '                eligible: runtime?.eligible ?? hard?.eligible ?? true,\n'
        '                deterministic_score: runtime?.deterministic_score ?? 0,\n'
        '                minimum_score: runtime?.minimum_score ?? hard?.minimumScore ?? 0,\n'
        '                signals: runtime?.signals ?? hard?.signals ?? {}\n'
        '              };\n'
        '            })\n',
        "relay resolver base evidence body",
    )

    text = replace_once(
        text,
        '        dimension: resolved.dimension,\n'
        '        candidates: resolved.candidates.map((candidate) => ({\n',
        '        dimension: resolved.dimension,\n'
        '        shadow_speaker_plan: resolved.shadow_speaker_plan ?? [],\n'
        '        shadow_candidate_scores: resolved.candidates.map((candidate) => ({\n'
        '          deployment_id: candidate.deployment_id,\n'
        '          deterministic_score: candidate.deterministic_score,\n'
        '          semantic_points: candidate.semantic_points,\n'
        '          shadow_final_score: candidate.shadow_final_score,\n'
        '          shadow_selected: candidate.shadow_selected\n'
        '        })),\n'
        '        speaker_plan_authoritative: resolved.speaker_plan_authoritative ?? false,\n'
        '        candidates: resolved.candidates.map((candidate) => ({\n',
        "relay expose shadow evidence",
    )
    RELAY.write_text(text, encoding="utf-8")


def write_test() -> None:
    TEST.write_text(
        '''import { afterEach, describe, expect, it, vi } from "vitest";\n\nimport { RelayClient } from "./relayClient.js";\nimport {\n  buildSmartParticipationBaseEvidence,\n  configureSmartParticipation,\n  resetSmartParticipationState\n} from "./smartParticipation.js";\nimport type { DiscordDeployment } from "./types.js";\n\nfunction deployment(name: string): DiscordDeployment {\n  return {\n    deployment_id: `deployment-${name}`,\n    connection_id: "connection-1",\n    character_card_id: `card-${name}`,\n    character_display_name: name,\n    workspace_id: "guild-1",\n    workspace_name: "Guild",\n    channel_id: "channel-1",\n    channel_name: "general",\n    thread_id: "",\n    thread_name: "",\n    category_id: "",\n    server_profile_id: "",\n    channel_scope_mode: "exact",\n    excluded_channel_ids: [],\n    excluded_category_ids: [],\n    participation_mode: "smart",\n    version_label: "Current",\n    status: "active",\n    identity_mode: "webhook",\n    identity_display_name: name,\n    identity_avatar_url: "",\n    address_aliases: [name],\n    webhook_status: "pending",\n    webhook_id: null,\n    webhook_token: null,\n    orchestration_mode: "off"\n  };\n}\n\nfunction jsonResponse(value: unknown): Response {\n  return new Response(JSON.stringify(value), {\n    status: 200,\n    headers: { "Content-Type": "application/json" }\n  });\n}\n\ndescribe("V4 deterministic shadow bridge", () => {\n  afterEach(() => {\n    vi.unstubAllGlobals();\n    resetSmartParticipationState();\n  });\n\n  it("exports the same zero-semantic candidate score used by the TS scorer", () => {\n    const ann = deployment("Ann");\n    configureSmartParticipation({\n      enabled: true,\n      profiles: {\n        [ann.deployment_id]: {\n          style: "balanced",\n          topics: ["photography"],\n          keywords: ["lens"],\n          cooldown_seconds: 0\n        }\n      }\n    });\n\n    const evidence = buildSmartParticipationBaseEvidence(\n      [ann],\n      "photography lens question",\n      1_000\n    );\n\n    expect(evidence).toHaveLength(1);\n    expect(evidence[0]?.deploymentId).toBe(ann.deployment_id);\n    expect(evidence[0]?.eligible).toBe(true);\n    expect(evidence[0]?.minimumScore).toBe(5);\n    expect(evidence[0]?.signals.topic_match).toBe(3);\n    expect(evidence[0]?.signals.keyword_match).toBe(2);\n    expect(evidence[0]?.signals.semantic_match).toBe(0);\n    expect(evidence[0]?.deterministicScore).toBeGreaterThanOrEqual(5);\n  });\n\n  it("forwards deterministic evidence and surfaces server shadow scores without using them for selection", async () => {\n    const ann = deployment("Ann");\n    const resolverBodies: Array<Record<string, unknown>> = [];\n    vi.stubGlobal(\n      "fetch",\n      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {\n        const url = new URL(\n          typeof input === "string" ? input : input instanceof URL ? input.href : input.url\n        );\n        if (url.pathname === "/api/connectors/discord/deployments") return jsonResponse([ann]);\n        if (url.pathname === "/api/smart-participation/connector-profiles") return jsonResponse({});\n        if (url.pathname === "/api/smart-participation/resolve") {\n          resolverBodies.push(\n            JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>\n          );\n          return jsonResponse({\n            resolver_version: "conversation-intelligence-v4-shadow-2",\n            available: true,\n            reason: "ok",\n            model: "e5",\n            dimension: 1024,\n            burst_id: "",\n            burst_message_count: 1,\n            analysis_chars: 20,\n            candidates: [\n              {\n                deployment_id: ann.deployment_id,\n                character_card_id: ann.character_card_id,\n                eligible: true,\n                deterministic_score: 4.5,\n                minimum_score: 5,\n                deterministic_signals: { initiative: 0.5 },\n                raw_e5_relevance: 0.9,\n                profile_ready: true,\n                semantic_points: 6,\n                shadow_final_score: 10.5,\n                shadow_selected: true,\n                graph_evidence_count: 0,\n                learned_state_evidence_count: 0,\n                utility_adjustment: 0\n              }\n            ],\n            speaker_plan: [],\n            shadow_speaker_plan: [\n              { deployment_id: ann.deployment_id, turn_role: "primary", reason: "deterministic_e5_shadow" }\n            ],\n            speaker_plan_authoritative: false,\n            graph_shadow_observed: false,\n            graph_shadow_node_count: 0,\n            graph_shadow_edge_count: 0,\n            graph_used: false,\n            learned_state_used: false,\n            utility_used: false\n          });\n        }\n        throw new Error(`unexpected request ${url.pathname}`);\n      })\n    );\n\n    const relay = new RelayClient("https://relay.example.test", "token", "connection-1");\n    await relay.listDeployments();\n    const result = await relay.scoreSmartParticipation({\n      message: "ordinary unresolved message",\n      deployment_ids: [ann.deployment_id],\n      minimum_margin: 2,\n      max_participants: 2,\n      candidate_preflight: [\n        {\n          deployment_id: ann.deployment_id,\n          eligible: true,\n          deterministic_score: 4.5,\n          minimum_score: 5,\n          signals: { initiative: 0.5 }\n        }\n      ]\n    });\n\n    expect(resolverBodies[0]).toMatchObject({\n      minimum_margin: 2,\n      max_participants: 2,\n      candidates: [\n        {\n          deployment_id: ann.deployment_id,\n          deterministic_score: 4.5,\n          minimum_score: 5,\n          signals: { initiative: 0.5 }\n        }\n      ]\n    });\n    expect(result.speaker_plan_authoritative).toBe(false);\n    expect(result.shadow_speaker_plan?.[0]?.deployment_id).toBe(ann.deployment_id);\n    expect(result.shadow_candidate_scores?.[0]?.shadow_final_score).toBe(10.5);\n    expect(result.candidates[0]?.semantic_relevance).toBe(0.9);\n  });\n});\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_smart()
    patch_index()
    patch_relay()
    write_test()
