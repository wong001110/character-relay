import {
  configureSmartParticipation,
  parseSmartParticipationProfiles,
  type SmartParticipationProfiles
} from "./smartParticipation.js";

export interface ConnectorConfig {
  discordBotToken: string;
  relayApiUrl: string;
  relayConnectorToken: string;
  relayConnectionId: string;
  port: number;
  deploymentRefreshSeconds: number;
  heartbeatSeconds: number;
  maxContextMessages: number;
  messageContentIntent: boolean;
  smartParticipationEnabled: boolean;
  smartParticipationProfiles: SmartParticipationProfiles;
  smartParticipationMinimumMargin: number;
  smartParticipationMaxParticipants: number;
  smartParticipationChannelCooldownSeconds: number;
  smartParticipationWindowSeconds: number;
  smartParticipationMaxRepliesPerWindow: number;
  smartParticipationLightweightFollowUpWindowSeconds: number;
  smartParticipationTurnCollectorEnabled: boolean;
  smartParticipationTurnCollectorQuietMs: number;
  smartParticipationTurnCollectorMaxWaitMs: number;
  smartParticipationTurnCollectorMaxMessages: number;
  smartParticipationTurnCollectorMaxCharacters: number;
  groupAddressAliases: string[];
  botTagConversationsEnabled: boolean;
  botTagMaxDepth: number;
  botTagMaxResponses: number;
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function integer(name: string, fallback: number, minimum: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < minimum) {
    throw new Error(`${name} must be an integer greater than or equal to ${minimum}.`);
  }
  return parsed;
}

function boundedInteger(
  name: string,
  fallback: number,
  minimum: number,
  maximum: number
): number {
  const value = integer(name, fallback, minimum);
  if (value > maximum) {
    throw new Error(`${name} must be less than or equal to ${maximum}.`);
  }
  return value;
}

function boolean(name: string, fallback = false): boolean {
  const raw = process.env[name]?.trim().toLowerCase();
  if (!raw) return fallback;
  if (["1", "true", "yes", "on"].includes(raw)) return true;
  if (["0", "false", "no", "off"].includes(raw)) return false;
  throw new Error(`${name} must be true or false.`);
}

function stringList(name: string): string[] {
  const raw = process.env[name]?.trim();
  if (!raw) return [];
  return [
    ...new Set(
      raw
        .split(/\r?\n|,/u)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  ];
}

export function loadConfig(): ConnectorConfig {
  const config: ConnectorConfig = {
    discordBotToken: required("DISCORD_BOT_TOKEN"),
    relayApiUrl: required("CHARACTER_RELAY_API_URL").replace(/\/$/, ""),
    relayConnectorToken: required("CHARACTER_RELAY_CONNECTOR_TOKEN"),
    relayConnectionId: required("CHARACTER_RELAY_CONNECTION_ID"),
    port: integer("PORT", 3000, 1),
    deploymentRefreshSeconds: integer("DEPLOYMENT_REFRESH_SECONDS", 30, 5),
    heartbeatSeconds: integer("HEARTBEAT_SECONDS", 30, 10),
    maxContextMessages: integer("MAX_CONTEXT_MESSAGES", 20, 1),
    messageContentIntent: boolean("DISCORD_MESSAGE_CONTENT_INTENT", false),
    smartParticipationEnabled: boolean("DISCORD_SMART_PARTICIPATION_ENABLED", false),
    smartParticipationProfiles: parseSmartParticipationProfiles(
      process.env.DISCORD_SMART_PARTICIPATION_PROFILES_JSON
    ),
    smartParticipationMinimumMargin: integer(
      "DISCORD_SMART_PARTICIPATION_MINIMUM_MARGIN",
      2,
      0
    ),
    smartParticipationMaxParticipants: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_MAX_PARTICIPANTS",
      2,
      1,
      3
    ),
    smartParticipationChannelCooldownSeconds: integer(
      "DISCORD_SMART_PARTICIPATION_CHANNEL_COOLDOWN_SECONDS",
      45,
      0
    ),
    smartParticipationWindowSeconds: integer(
      "DISCORD_SMART_PARTICIPATION_WINDOW_SECONDS",
      600,
      1
    ),
    smartParticipationMaxRepliesPerWindow: integer(
      "DISCORD_SMART_PARTICIPATION_MAX_REPLIES_PER_WINDOW",
      3,
      1
    ),
    smartParticipationLightweightFollowUpWindowSeconds: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_LIGHTWEIGHT_FOLLOW_UP_WINDOW_SECONDS",
      90,
      1,
      600
    ),
    smartParticipationTurnCollectorEnabled: boolean(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_ENABLED",
      true
    ),
    smartParticipationTurnCollectorQuietMs: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_QUIET_MS",
      1_500,
      100,
      10_000
    ),
    smartParticipationTurnCollectorMaxWaitMs: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_MAX_WAIT_MS",
      4_000,
      500,
      30_000
    ),
    smartParticipationTurnCollectorMaxMessages: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_MAX_MESSAGES",
      5,
      1,
      20
    ),
    smartParticipationTurnCollectorMaxCharacters: boundedInteger(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_MAX_CHARACTERS",
      1_500,
      100,
      10_000
    ),
    groupAddressAliases: stringList("DISCORD_GROUP_ADDRESS_ALIASES"),
    botTagConversationsEnabled: boolean(
      "DISCORD_BOT_TAG_CONVERSATIONS_ENABLED",
      true
    ),
    botTagMaxDepth: boundedInteger("DISCORD_BOT_TAG_MAX_DEPTH", 4, 1, 12),
    botTagMaxResponses: boundedInteger(
      "DISCORD_BOT_TAG_MAX_RESPONSES",
      8,
      1,
      30
    )
  };
  if (
    config.smartParticipationTurnCollectorMaxWaitMs <
    config.smartParticipationTurnCollectorQuietMs
  ) {
    throw new Error(
      "DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_MAX_WAIT_MS must be greater than or equal to DISCORD_SMART_PARTICIPATION_TURN_COLLECTOR_QUIET_MS."
    );
  }
  configureSmartParticipation({
    enabled: config.smartParticipationEnabled,
    profiles: config.smartParticipationProfiles,
    minimumMargin: config.smartParticipationMinimumMargin,
    maxParticipants: config.smartParticipationMaxParticipants,
    channelCooldownSeconds: config.smartParticipationChannelCooldownSeconds,
    windowSeconds: config.smartParticipationWindowSeconds,
    maxRepliesPerWindow: config.smartParticipationMaxRepliesPerWindow,
    lightweightFollowUpWindowSeconds:
      config.smartParticipationLightweightFollowUpWindowSeconds
  });
  return config;
}
