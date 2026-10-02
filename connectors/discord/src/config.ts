

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
  ambientParticipationEnabled: boolean;
  roomBufferEnabled: boolean;
  roomBufferQuietMs: number;
  roomBufferMaxWaitMs: number;
  roomBufferMaxMessages: number;
  roomBufferMaxCharacters: number;
  groupAddressAliases: string[];
  botContinuationEnabled: boolean;
  conversationMaxDepth: number;
  conversationMaxResponses: number;
  turnJobMaxWaitMs: number;
  turnJobRecoveryMaxConcurrent: number;
  turnIngressMaxPending: number;
  turnIngressMaxPendingPerDestination: number;
  turnIngressMaxPreflightAgeMs: number;
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function integer(name: string, fallback: number, minimum: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < minimum) {
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
    ambientParticipationEnabled: boolean("DISCORD_AMBIENT_PARTICIPATION_ENABLED", false),
    roomBufferEnabled: boolean(
      "DISCORD_ROOM_BUFFER_ENABLED",
      true
    ),
    roomBufferQuietMs: boundedInteger(
      "DISCORD_ROOM_BUFFER_QUIET_MS",
      3_000,
      100,
      10_000
    ),
    roomBufferMaxWaitMs: boundedInteger(
      "DISCORD_ROOM_BUFFER_MAX_WAIT_MS",
      10_000,
      500,
      30_000
    ),
    roomBufferMaxMessages: boundedInteger(
      "DISCORD_ROOM_BUFFER_MAX_MESSAGES",
      5,
      1,
      20
    ),
    roomBufferMaxCharacters: boundedInteger(
      "DISCORD_ROOM_BUFFER_MAX_CHARACTERS",
      1_500,
      100,
      10_000
    ),
    groupAddressAliases: stringList("DISCORD_GROUP_ADDRESS_ALIASES"),
    botContinuationEnabled: boolean(
      "DISCORD_BOT_CONTINUATION_ENABLED",
      true
    ),
    conversationMaxDepth: boundedInteger("DISCORD_CONVERSATION_MAX_DEPTH", 4, 1, 12),
    conversationMaxResponses: boundedInteger(
      "DISCORD_CONVERSATION_MAX_RESPONSES",
      6,
      1,
      30
    ),
    turnJobMaxWaitMs: boundedInteger(
      "DISCORD_TURN_JOB_MAX_WAIT_MS",
      330_000,
      30_000,
      960_000
    ),
    turnJobRecoveryMaxConcurrent: boundedInteger(
      "DISCORD_TURN_JOB_RECOVERY_MAX_CONCURRENT",
      4,
      1,
      10
    ),
    turnIngressMaxPending: boundedInteger(
      "DISCORD_TURN_INGRESS_MAX_PENDING",
      100,
      1,
      1_000
    ),
    turnIngressMaxPendingPerDestination: boundedInteger(
      "DISCORD_TURN_INGRESS_MAX_PENDING_PER_DESTINATION",
      8,
      1,
      100
    ),
    turnIngressMaxPreflightAgeMs: boundedInteger(
      "DISCORD_TURN_INGRESS_MAX_PREFLIGHT_AGE_MS",
      30_000,
      1_000,
      300_000
    )
  };
  if (
    config.roomBufferMaxWaitMs <
    config.roomBufferQuietMs
  ) {
    throw new Error(
      "DISCORD_ROOM_BUFFER_MAX_WAIT_MS must be greater than or equal to DISCORD_ROOM_BUFFER_QUIET_MS."
    );
  }
  return config;
}
