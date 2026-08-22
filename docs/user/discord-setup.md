# Set up Discord

This guide takes one Discord Bot from the Discord Developer Portal to a working Character reply. Keep Bot tokens, provider keys, and connector secrets outside Git and screenshots.

## 1. Prepare Discord

Create an Application and Bot in the Discord Developer Portal. Invite the Bot with the `bot` OAuth scope and only these minimum permissions:

```text
View Channels
Send Messages
Send Messages in Threads
Read Message History
Manage Webhooks
```

Administrator is not required. Enable **Message Content Intent** for the Bot; ordinary message context, reply routing, and Smart Participation depend on it.

## 2. Prepare Character Relay

The configured Bootstrap Super Admin creates the managed Discord Connection. In the Portal:

1. Create or select the Character Card you want to deploy.
2. Open **Deployment Center** and add a Discord Connection (Super Admin only).
3. Copy its Connection ID.
4. Create a Server Profile from a Discord Server synchronized by that Connection.
5. Create an Active Character Deployment in that Server workspace and choose its Channel or Thread.

Regular users cannot create managed Connections. They select/claim a Server already synchronized by the operator, then create their Character Deployment in that Server workspace. New Connection and Deployment creation is Discord-only. A Character Card can be deployed more than once, but every Deployment keeps its own Server and destination scope.

## 3. Configure the shared secret

Set one random secret on the Character Relay API:

```text
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random secret>
```

Set the same value on the Discord Connector under a different setting name:

```text
CHARACTER_RELAY_CONNECTOR_TOKEN=<same secret>
```

Do not paste either value into a Character Card, document, log, or issue.

## 4. Start the Connector

The Connector requires:

```text
DISCORD_BOT_TOKEN=<Discord Bot token>
CHARACTER_RELAY_API_URL=https://<Character Relay service domain>
CHARACTER_RELAY_CONNECTOR_TOKEN=<shared secret>
CHARACTER_RELAY_CONNECTION_ID=<Connection ID from Deployment Center>
DISCORD_MESSAGE_CONTENT_INTENT=true
```

For local development, copy `connectors/discord/.env.example` to `.env`, fill the values, then run:

```bash
cd connectors/discord
npm install
npm run dev
```

## 5. Verify the path

1. Open the Connector `/health` endpoint and confirm it has refreshed deployments.
2. Confirm the Deployment is Active and its Server, Channel, and optional Thread match Discord.
3. Send `@CharacterRelayBot hello` in the allowed destination.
4. If multiple Characters share it, include the Character name after the Bot mention.
5. Reply directly to the Character message and confirm it routes back to the same Deployment.

If this fails, follow [Discord debugging](discord-debugging.md). Advanced addressing, group aliases, Bot-to-Bot Tag limits, Stickers, and Railway settings are documented in the [Connector reference](../../connectors/discord/README.md).
