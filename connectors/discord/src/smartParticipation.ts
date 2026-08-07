import type { DiscordDeployment } from "./types.js";

export interface SmartParticipationProfileInput {
  topics?: string[];
  keywords?: string[];
  trigger_phrases?: string[];
  avoid_phrases?: string[];
  initiative?: number;
  minimum_score?: number;
  cooldown_seconds?: number;
}

export type SmartParticipationProfiles = Record<string, SmartParticipationProfileInput>;

export interface SmartParticipationRuntimeConfig {
  enabled: boolean;
  profiles: SmartParticipationProfiles;
  minimumMargin: number;
  channelCooldownSeconds: number;
  windowSeconds: number;
  maxRepliesPerWindow: number;
}

export interface SmartParticipationSignals {
  question: number;
  help_request: number;
  name_match: number;
  topic_match: number;
  keyword_match: number;
  trigger_phrase: number;
  initiative: number;
  short_message_penalty: number;
  cooldown_blocked: number;
  avoid_phrase_blocked: number;
}

export interface SmartParticipationCandidateScore {
  deployment: DiscordDeployment;
  score: number;
  minimumScore: number;
  eligible: boolean;
  signals: SmartParticipationSignals;
  matchedTopics: string[];
  matchedKeywords: string[];
  matchedTriggerPhrases: string[];
  matchedAvoidPhrases: string[];
}

export type SmartParticipationReason =
  | "disabled"
  | "no_smart_candidates"
  | "empty_message"
  | "low_information_message"
  | "channel_cooldown"
  | "channel_rate_limit"
  | "below_threshold"
  | "ambiguous_margin"
  | "selected";

export interface SmartParticipationDecision {
  reason: SmartParticipationReason;
  selectedDeployment: DiscordDeployment | null;
  candidates: SmartParticipationCandidateScore[];
}

interface NormalizedProfile {
  topics: string[];
  keywords: string[];
  triggerPhrases: string[];
  avoidPhrases: string[];
  initiative: number;
  minimumScore: number;
  cooldownSeconds: number;
}

interface ProactiveSelection {
  deploymentId: string;
  scopeKey: string;
  selectedAt: number;
}

const DEFAULT_CONFIG: SmartParticipationRuntimeConfig = {
  enabled: false,
  profiles: {},
  minimumMargin: 2,
  channelCooldownSeconds: 45,
  windowSeconds: 600,
  maxRepliesPerWindow: 3
};

const LOW_INFORMATION_MESSAGES = new Set([
  "ok",
  "okay",
  "k",
  "yes",
  "no",
  "yep",
  "nope",
  "lol",
  "lmao",
  "haha",
  "thanks",
  "thank you",
  "好的",
  "好",
  "嗯",
  "哦",
  "噢",
  "哈哈",
  "收到",
  "谢谢",
  "謝謝",
  "晚安",
  "早",
  "早安"
]);

const QUESTION_PHRASES = [
  "why",
  "what",
  "when",
  "where",
  "which",
  "who",
  "how",
  "can i",
  "can we",
  "could you",
  "does anyone",
  "is there",
  "为什么",
  "為什麼",
  "怎么",
  "怎麼",
  "如何",
  "谁知道",
  "誰知道",
  "能不能",
  "可不可以",
  "有没有",
  "有沒有"
];

const HELP_PHRASES = [
  "help",
  "need help",
  "any idea",
  "does anyone know",
  "can someone",
  "could someone",
  "stuck",
  "not working",
  "doesn't work",
  "does not work",
  "帮忙",
  "幫忙",
  "帮我",
  "幫我",
  "有人知道",
  "卡住",
  "没反应",
  "沒反應",
  "不能用",
  "无法",
  "無法",
  "出错",
  "出錯"
];

let runtimeConfig: SmartParticipationRuntimeConfig = { ...DEFAULT_CONFIG };
let runtimeConfigured = false;
const pendingSmartSelections = new Set<string>();
let proactiveSelections: ProactiveSelection[] = [];

export function configureSmartParticipation(
  config: Partial<SmartParticipationRuntimeConfig>
): void {
  runtimeConfig = {
    ...DEFAULT_CONFIG,
    ...config,
    profiles: config.profiles ?? {}
  };
  runtimeConfigured = true;
}

export function parseSmartParticipationProfiles(raw: string | undefined): SmartParticipationProfiles {
  if (!raw?.trim()) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(
      `DISCORD_SMART_PARTICIPATION_PROFILES_JSON must be valid JSON: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("DISCORD_SMART_PARTICIPATION_PROFILES_JSON must be a JSON object.");
  }
  const profiles: SmartParticipationProfiles = {};
  for (const [key, value] of Object.entries(parsed)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`Smart Participation profile ${key} must be a JSON object.`);
    }
    const input = value as Record<string, unknown>;
    const profile: SmartParticipationProfileInput = {};
    const topics = stringArray(input.topics, `${key}.topics`);
    const keywords = stringArray(input.keywords, `${key}.keywords`);
    const triggerPhrases = stringArray(
      input.trigger_phrases,
      `${key}.trigger_phrases`
    );
    const avoidPhrases = stringArray(input.avoid_phrases, `${key}.avoid_phrases`);
    const initiative = optionalNumber(input.initiative, `${key}.initiative`);
    const minimumScore = optionalNumber(input.minimum_score, `${key}.minimum_score`);
    const cooldownSeconds = optionalNumber(
      input.cooldown_seconds,
      `${key}.cooldown_seconds`
    );
    if (topics !== undefined) profile.topics = topics;
    if (keywords !== undefined) profile.keywords = keywords;
    if (triggerPhrases !== undefined) profile.trigger_phrases = triggerPhrases;
    if (avoidPhrases !== undefined) profile.avoid_phrases = avoidPhrases;
    if (initiative !== undefined) profile.initiative = initiative;
    if (minimumScore !== undefined) profile.minimum_score = minimumScore;
    if (cooldownSeconds !== undefined) profile.cooldown_seconds = cooldownSeconds;
    profiles[key] = profile;
  }
  return profiles;
}

function stringArray(value: unknown, field: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must be an array of strings.`);
  }
  return [...new Set(value.map((item) => item.trim()).filter(Boolean))];
}

function optionalNumber(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${field} must be a finite number.`);
  }
  return value;
}

function normalizeText(value: string): string {
  return value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/gu, " ").trim();
}

function normalizeList(values: string[] | undefined): string[] {
  return [...new Set((values ?? []).map(normalizeText).filter(Boolean))];
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizedProfile(profile: SmartParticipationProfileInput | undefined): NormalizedProfile {
  return {
    topics: normalizeList(profile?.topics),
    keywords: normalizeList(profile?.keywords),
    triggerPhrases: normalizeList(profile?.trigger_phrases),
    avoidPhrases: normalizeList(profile?.avoid_phrases),
    initiative: clamp(profile?.initiative ?? 0, 0, 1),
    minimumScore: clamp(profile?.minimum_score ?? 5, 0, 100),
    cooldownSeconds: clamp(profile?.cooldown_seconds ?? 120, 0, 86_400)
  };
}

function profileFor(deployment: DiscordDeployment): NormalizedProfile {
  const keys = [
    `deployment:${deployment.deployment_id}`,
    deployment.deployment_id,
    `character:${deployment.character_card_id}`,
    deployment.character_card_id,
    `name:${deployment.character_display_name}`,
    deployment.character_display_name,
    `name:${deployment.identity_display_name}`,
    deployment.identity_display_name,
    "default"
  ].filter(Boolean);
  for (const key of keys) {
    const profile = runtimeConfig.profiles[key];
    if (profile) return normalizedProfile(profile);
  }
  return normalizedProfile(undefined);
}

function scopeKey(deployment: DiscordDeployment): string {
  return [
    deployment.connection_id,
    deployment.workspace_id,
    deployment.channel_id,
    deployment.thread_id
  ].join(":");
}

function matchedPhrases(text: string, phrases: string[]): string[] {
  return phrases.filter((phrase) => phrase && text.includes(phrase));
}

function nameValues(deployment: DiscordDeployment): string[] {
  return normalizeList([
    deployment.character_display_name,
    deployment.identity_display_name,
    ...(deployment.address_aliases ?? [])
  ]);
}

function isQuestion(text: string): boolean {
  return /[?？]/u.test(text) || QUESTION_PHRASES.some((phrase) => text.includes(phrase));
}

function isHelpRequest(text: string): boolean {
  return HELP_PHRASES.some((phrase) => text.includes(phrase));
}

function isLowInformation(text: string): boolean {
  const stripped = text.replace(/[\s.,!?，。！？~～…]+/gu, "").trim();
  return stripped.length <= 16 && LOW_INFORMATION_MESSAGES.has(stripped);
}

function pruneSelections(now: number): void {
  const retentionMilliseconds = Math.max(
    runtimeConfig.windowSeconds,
    86_400
  ) * 1000;
  proactiveSelections = proactiveSelections.filter(
    (item) => now - item.selectedAt <= retentionMilliseconds
  );
}

function clearPending(deployments: DiscordDeployment[]): void {
  for (const deployment of deployments) {
    pendingSmartSelections.delete(deployment.deployment_id);
  }
}

function emptySignals(): SmartParticipationSignals {
  return {
    question: 0,
    help_request: 0,
    name_match: 0,
    topic_match: 0,
    keyword_match: 0,
    trigger_phrase: 0,
    initiative: 0,
    short_message_penalty: 0,
    cooldown_blocked: 0,
    avoid_phrase_blocked: 0
  };
}

function scoreCandidate(
  deployment: DiscordDeployment,
  text: string,
  now: number
): SmartParticipationCandidateScore {
  const profile = profileFor(deployment);
  const signals = emptySignals();
  const matchedAvoidPhrases = matchedPhrases(text, profile.avoidPhrases);
  if (matchedAvoidPhrases.length) {
    signals.avoid_phrase_blocked = 1;
    return {
      deployment,
      score: Number.NEGATIVE_INFINITY,
      minimumScore: profile.minimumScore,
      eligible: false,
      signals,
      matchedTopics: [],
      matchedKeywords: [],
      matchedTriggerPhrases: [],
      matchedAvoidPhrases
    };
  }

  const lastSelection = proactiveSelections
    .filter((item) => item.deploymentId === deployment.deployment_id)
    .sort((left, right) => right.selectedAt - left.selectedAt)[0];
  if (
    lastSelection &&
    now - lastSelection.selectedAt < profile.cooldownSeconds * 1000
  ) {
    signals.cooldown_blocked = 1;
    return {
      deployment,
      score: Number.NEGATIVE_INFINITY,
      minimumScore: profile.minimumScore,
      eligible: false,
      signals,
      matchedTopics: [],
      matchedKeywords: [],
      matchedTriggerPhrases: [],
      matchedAvoidPhrases: []
    };
  }

  const matchedTopics = matchedPhrases(text, profile.topics);
  const matchedKeywords = matchedPhrases(text, profile.keywords);
  const matchedTriggerPhrases = matchedPhrases(text, profile.triggerPhrases);
  const names = matchedPhrases(text, nameValues(deployment));

  signals.question = isQuestion(text) ? 2 : 0;
  signals.help_request = isHelpRequest(text) ? 2 : 0;
  signals.name_match = names.length ? 5 : 0;
  signals.topic_match = Math.min(6, matchedTopics.length * 3);
  signals.keyword_match = Math.min(6, matchedKeywords.length * 2);
  signals.trigger_phrase = Math.min(4, matchedTriggerPhrases.length * 2);
  signals.initiative = profile.initiative;
  signals.short_message_penalty = text.length < 4 ? -2 : 0;

  const score = Object.values(signals).reduce((total, value) => total + value, 0);
  return {
    deployment,
    score: Math.round(score * 1000) / 1000,
    minimumScore: profile.minimumScore,
    eligible: true,
    signals,
    matchedTopics,
    matchedKeywords,
    matchedTriggerPhrases,
    matchedAvoidPhrases: []
  };
}

function logDecision(decision: SmartParticipationDecision, messageLength: number): void {
  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      message: "Deterministic Smart Participation decision.",
      event_type: "smart_participation_decision",
      reason: decision.reason,
      message_length: messageLength,
      selected_deployment_id: decision.selectedDeployment?.deployment_id ?? null,
      candidates: decision.candidates.map((candidate) => ({
        deployment_id: candidate.deployment.deployment_id,
        character_card_id: candidate.deployment.character_card_id,
        score: Number.isFinite(candidate.score) ? candidate.score : null,
        minimum_score: candidate.minimumScore,
        eligible: candidate.eligible,
        signals: candidate.signals,
        matched_topics: candidate.matchedTopics,
        matched_keywords: candidate.matchedKeywords,
        matched_trigger_phrases: candidate.matchedTriggerPhrases,
        matched_avoid_phrases: candidate.matchedAvoidPhrases
      }))
    })
  );
}

function decision(
  reason: SmartParticipationReason,
  selectedDeployment: DiscordDeployment | null,
  candidates: SmartParticipationCandidateScore[],
  messageLength: number
): SmartParticipationDecision {
  const value: SmartParticipationDecision = { reason, selectedDeployment, candidates };
  if (runtimeConfig.enabled) logDecision(value, messageLength);
  return value;
}

export function evaluateSmartParticipation(
  deployments: DiscordDeployment[],
  message: string,
  now = Date.now()
): SmartParticipationDecision {
  clearPending(deployments);
  if (!runtimeConfig.enabled) {
    return { reason: "disabled", selectedDeployment: null, candidates: [] };
  }
  const smartCandidates = deployments.filter(
    (deployment) => deployment.participation_mode === "smart"
  );
  if (!smartCandidates.length) {
    return { reason: "no_smart_candidates", selectedDeployment: null, candidates: [] };
  }

  const text = normalizeText(message);
  if (!text) return decision("empty_message", null, [], 0);
  if (isLowInformation(text)) {
    return decision("low_information_message", null, [], text.length);
  }

  pruneSelections(now);
  const scope = scopeKey(smartCandidates[0]!);
  const scopeSelections = proactiveSelections
    .filter((item) => item.scopeKey === scope)
    .sort((left, right) => right.selectedAt - left.selectedAt);
  const latest = scopeSelections[0];
  if (
    latest &&
    now - latest.selectedAt < runtimeConfig.channelCooldownSeconds * 1000
  ) {
    return decision("channel_cooldown", null, [], text.length);
  }
  const windowStart = now - runtimeConfig.windowSeconds * 1000;
  if (
    scopeSelections.filter((item) => item.selectedAt >= windowStart).length >=
    runtimeConfig.maxRepliesPerWindow
  ) {
    return decision("channel_rate_limit", null, [], text.length);
  }

  const candidates = smartCandidates
    .map((deployment) => scoreCandidate(deployment, text, now))
    .sort((left, right) => {
      if (left.eligible !== right.eligible) return left.eligible ? -1 : 1;
      if (left.score !== right.score) return right.score - left.score;
      return left.deployment.deployment_id.localeCompare(right.deployment.deployment_id);
    });
  const top = candidates.find((candidate) => candidate.eligible);
  if (!top || top.score < top.minimumScore) {
    return decision("below_threshold", null, candidates, text.length);
  }
  const runnerUp = candidates.find(
    (candidate) =>
      candidate.eligible && candidate.deployment.deployment_id !== top.deployment.deployment_id
  );
  if (runnerUp && top.score - runnerUp.score < runtimeConfig.minimumMargin) {
    return decision("ambiguous_margin", null, candidates, text.length);
  }

  pendingSmartSelections.add(top.deployment.deployment_id);
  proactiveSelections.push({
    deploymentId: top.deployment.deployment_id,
    scopeKey: scopeKey(top.deployment),
    selectedAt: now
  });
  return decision("selected", top.deployment, candidates, text.length);
}

export function markExplicitSmartSelections(deployments: DiscordDeployment[]): void {
  clearPending(deployments);
  for (const deployment of deployments) {
    if (deployment.participation_mode === "smart") {
      pendingSmartSelections.add(deployment.deployment_id);
    }
  }
}

export function consumeSmartSelection(deploymentId: string): boolean {
  if (!runtimeConfigured) return true;
  const selected = pendingSmartSelections.has(deploymentId);
  pendingSmartSelections.delete(deploymentId);
  return selected;
}

export function resetSmartParticipationState(): void {
  runtimeConfig = { ...DEFAULT_CONFIG };
  runtimeConfigured = false;
  pendingSmartSelections.clear();
  proactiveSelections = [];
}
