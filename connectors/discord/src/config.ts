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
  groupAddressAliases: string[];
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
  return {
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
    groupAddressAliases: stringList("DISCORD_GROUP_ADDRESS_ALIASES")
  };
}
