import type { DiscordDeployment } from "./types.js";

export type SmartParticipationStyle = "quiet" | "balanced" | "active";
export type SmartParticipationGroupRole = "primary" | "secondary" | "independent";
export interface DiscordPortalParticipationProfile {
  character_card_id: string; configured: boolean; enabled: boolean;
  style: SmartParticipationStyle; group_role: SmartParticipationGroupRole;
  topics: string[]; keywords: string[]; trigger_phrases: string[]; avoid_phrases: string[];
  cooldown_seconds: number; preferred_follow_up_character_card_id: string; follow_up_window_seconds: number;
  created_at?: string | null; updated_at?: string | null;
}
export interface SmartParticipationProfileInput { enabled?: boolean; avoid_phrases?: string[]; cooldown_seconds?: number; }
export type SmartParticipationProfiles = Record<string, SmartParticipationProfileInput>;
export interface SmartParticipationRuntimeConfig { enabled: boolean; profiles: SmartParticipationProfiles; channelCooldownSeconds: number; windowSeconds: number; maxRepliesPerWindow: number; }
export type SmartParticipationHardGateReason = "resolver_required" | "disabled" | "no_smart_candidates" | "empty_message" | "channel_cooldown" | "channel_rate_limit" | "all_candidates_blocked";
export interface SmartParticipationHardPreflight { skipResolver: boolean; reason: SmartParticipationHardGateReason; eligibleDeploymentIds: string[]; }
interface NormalizedProfile { enabled: boolean; avoidPhrases: string[]; cooldownSeconds: number; }
interface PendingSelection { origin: "explicit" | "v3"; scopeKey: string; selectedAt: number; }
interface V3Admission { deploymentId: string; scopeKey: string; admittedAt: number; }

const DEFAULT_CONFIG: SmartParticipationRuntimeConfig = { enabled: false, profiles: {}, channelCooldownSeconds: 45, windowSeconds: 600, maxRepliesPerWindow: 3 };
let runtimeConfig: SmartParticipationRuntimeConfig = { ...DEFAULT_CONFIG };
const pendingSelections = new Map<string, PendingSelection>();
let v3Admissions: V3Admission[] = [];

function normalizeText(value: string): string { return value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/gu, " ").trim(); }
function scopeKey(deployment: DiscordDeployment): string { return [deployment.connection_id, deployment.workspace_id, deployment.channel_id, deployment.thread_id].map((item) => item.trim()).join(":"); }
function stringArray(value: unknown): string[] | undefined { return Array.isArray(value) && value.every((item) => typeof item === "string") ? [...new Set(value.map((item) => item.trim()).filter(Boolean))] : undefined; }
function normalizedProfile(input: SmartParticipationProfileInput | undefined): NormalizedProfile { return { enabled: input?.enabled ?? true, avoidPhrases: (input?.avoid_phrases ?? []).map(normalizeText).filter(Boolean), cooldownSeconds: Math.max(0, input?.cooldown_seconds ?? 0) }; }

export function configureSmartParticipation(config: Partial<SmartParticipationRuntimeConfig>): void {
  runtimeConfig = { ...runtimeConfig, ...config, profiles: config.profiles ?? runtimeConfig.profiles };
}
export function parseSmartParticipationProfiles(raw: string | undefined): SmartParticipationProfiles {
  if (!raw?.trim()) return {};
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { throw new Error("DISCORD_SMART_PARTICIPATION_PROFILES_JSON must be valid JSON."); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("DISCORD_SMART_PARTICIPATION_PROFILES_JSON must be a JSON object.");
  return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).flatMap(([key, value]) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const source = value as Record<string, unknown>; const profile: SmartParticipationProfileInput = {};
    if (typeof source.enabled === "boolean") profile.enabled = source.enabled;
    const avoidPhrases = stringArray(source.avoid_phrases); if (avoidPhrases !== undefined) profile.avoid_phrases = avoidPhrases;
    if (typeof source.cooldown_seconds === "number" && Number.isFinite(source.cooldown_seconds)) profile.cooldown_seconds = source.cooldown_seconds;
    return [[key, profile]];
  }));
}
export function smartParticipationProfileFor(deployment: DiscordDeployment): NormalizedProfile {
  const portal = (deployment as DiscordDeployment & { smart_participation_profile?: DiscordPortalParticipationProfile | null }).smart_participation_profile;
  if (portal?.configured) return normalizedProfile({ enabled: portal.enabled, avoid_phrases: portal.avoid_phrases, cooldown_seconds: portal.cooldown_seconds });
  return normalizedProfile(runtimeConfig.profiles[deployment.character_card_id] ?? runtimeConfig.profiles[deployment.deployment_id]);
}
function prune(now: number): void { const oldest = now - Math.max(runtimeConfig.windowSeconds, runtimeConfig.channelCooldownSeconds, 1) * 1000; v3Admissions = v3Admissions.filter((item) => item.admittedAt >= oldest); }
export function preflightSmartParticipationRuntime(deployments: DiscordDeployment[], message: string, now = Date.now(), runtimeScopeKey?: string): SmartParticipationHardPreflight {
  if (!runtimeConfig.enabled) return { skipResolver: true, reason: "disabled", eligibleDeploymentIds: [] };
  const smart = deployments.filter((item) => item.participation_mode === "smart");
  if (!smart.length) return { skipResolver: true, reason: "no_smart_candidates", eligibleDeploymentIds: [] };
  const text = normalizeText(message); if (!text) return { skipResolver: true, reason: "empty_message", eligibleDeploymentIds: [] };
  const scope = runtimeScopeKey?.trim() || scopeKey(smart[0]!); prune(now);
  const scoped = v3Admissions.filter((item) => item.scopeKey === scope).sort((left, right) => right.admittedAt - left.admittedAt);
  if (scoped[0] && now - scoped[0].admittedAt < runtimeConfig.channelCooldownSeconds * 1000) return { skipResolver: true, reason: "channel_cooldown", eligibleDeploymentIds: [] };
  if (scoped.filter((item) => item.admittedAt >= now - runtimeConfig.windowSeconds * 1000).length >= runtimeConfig.maxRepliesPerWindow) return { skipResolver: true, reason: "channel_rate_limit", eligibleDeploymentIds: [] };
  const eligibleDeploymentIds = smart.flatMap((deployment) => {
    const profile = smartParticipationProfileFor(deployment);
    if (!profile.enabled || profile.avoidPhrases.some((phrase) => text.includes(phrase))) return [];
    const last = v3Admissions.filter((item) => item.deploymentId === deployment.deployment_id).sort((left, right) => right.admittedAt - left.admittedAt)[0];
    return last && now - last.admittedAt < profile.cooldownSeconds * 1000 ? [] : [deployment.deployment_id];
  });
  return eligibleDeploymentIds.length ? { skipResolver: false, reason: "resolver_required", eligibleDeploymentIds } : { skipResolver: true, reason: "all_candidates_blocked", eligibleDeploymentIds: [] };
}
function mark(deployments: DiscordDeployment[], origin: PendingSelection["origin"], now: number, runtimeScopeKey?: string): void { for (const deployment of deployments) if (deployment.participation_mode === "smart") pendingSelections.set(deployment.deployment_id, { origin, scopeKey: runtimeScopeKey?.trim() || scopeKey(deployment), selectedAt: now }); }
export function markExplicitSmartSelections(deployments: DiscordDeployment[], now = Date.now(), runtimeScopeKey?: string): void { mark(deployments, "explicit", now, runtimeScopeKey); }
export function markV3SmartParticipationSelections(deployments: DiscordDeployment[], now = Date.now(), runtimeScopeKey?: string): void { mark(deployments, "v3", now, runtimeScopeKey); }
export function consumeSmartSelection(deploymentId: string): boolean { const pending = pendingSelections.get(deploymentId); pendingSelections.delete(deploymentId); if (!pending) return false; if (pending.origin === "v3") v3Admissions.push({ deploymentId, scopeKey: pending.scopeKey, admittedAt: pending.selectedAt }); return true; }
export function resetSmartParticipationState(): void { runtimeConfig = { ...DEFAULT_CONFIG }; pendingSelections.clear(); v3Admissions = []; }
